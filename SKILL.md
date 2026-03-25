---
name: synology-nas
description: Use when interacting with a Synology NAS — browsing files, managing downloads, scheduling tasks, or controlling containers via DSM API or SSH. Requires Claude Code CLI — does not work in the Claude.ai web UI.
---

# Synology NAS

> **CLI only.** On load, check `RUNNING_IN_CLI`. If `False`, immediately tell the user:
> *"The Synology NAS skill requires Claude Code CLI. It cannot run in the Claude.ai web UI — environment variables and local Python execution are not available here."*
> Then stop — do not attempt any operations.

Python library: `synology-api` v0.8.2. Optional SSH: `paramiko`.
Helper module: `tools/synology_client.py`. Service skills: `skills/`.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SYNOLOGY_HOST` | ✅ | — | NAS hostname or IP |
| `SYNOLOGY_PORT` | ✅ | `5001` | DSM HTTPS port |
| `SYNOLOGY_USER` | ✅ | — | DSM username |
| `SYNOLOGY_PASSWORD` | ✅ | — | DSM password |
| `SYNOLOGY_SSH_KEY_PATH` | — | — | SSH private key path (preferred over password) |
| `SYNOLOGY_SSH_PORT` | — | `22` | SSH port — **different from SYNOLOGY_PORT** |
| `SYNOLOGY_DOCKER_BIN` | — | `/var/packages/ContainerManager/target/usr/bin/docker` | Docker binary path on NAS |

**Never hardcode credentials.** Use environment variables only.

`SYNOLOGY_PORT` is the DSM web UI / API port (5001 HTTPS, 5000 HTTP).
`SYNOLOGY_SSH_PORT` is the SSH daemon port (22). These are different services.

---

## Quick Start

```python
# Install: pip install synology-api
# Optional SSH: pip install paramiko

from tools.synology_client import get_filestation, get_downloadstation
from tools.synology_client import get_taskscheduler, get_container_manager
from tools.synology_client import get_ssh, SSH_AVAILABLE

# Browse shares
fs = get_filestation()
result = fs.list_shares()
for share in result['data']['shares']:
    print(share['name'])

# Add a download
ds = get_downloadstation()
ds.add_url("magnet:?xt=urn:btih:abc123")
```

---

## API Patterns

**Always use factory functions.** Never instantiate library classes directly.

```python
fs  = get_filestation()       # SynologyFileStation
ds  = get_downloadstation()   # SynologyDownloadStation
ts  = get_taskscheduler()     # SynologyTaskScheduler
cm  = get_container_manager() # SynologyContainerManager
ssh = get_ssh()               # SynologySSH (not yet connected)
```

**Every method returns a dict.** Check `success` before accessing `data`:

```python
result = fs.list_dir("/volume1/data")
# _check_response() is called internally — SynologyAPIError raised on failure
# On success, result['data'] contains the payload
```

**Session sharing caveat:** `synology-api` uses a class-level shared session.
- Instantiating `FileStation` then `DownloadStation` reuses auth — only one login.
- `logout()` on any instance **invalidates all sessions**.
- On error code 119 (session expired, DSM default: 15 min): call the factory function again.
- Each service skill is independent — but session is shared; keep this in mind if using multiple modules together.

**Data envelope shapes vary by module** — the `data` key structure differs across services:

| Module | Data envelope |
|--------|--------------|
| FileStation | `result['data']['shares']`, `result['data']['files']`, etc. |
| DownloadStation | `result['data']['tasks']` |
| TaskScheduler | `result['data']['tasks']` for list; `result['data']` for results array |
| ContainerManager | `result['data']` directly (array of container objects) |

Always check the method example in the relevant service skill to see the correct envelope path.

**SSL:** Factory functions use `secure=True, cert_verify=False` (Synology self-signed certs).
For valid certs, instantiate library classes directly with `cert_verify=True`.

---

## Authorization Model

Every method is labeled with one of three tiers. The tier label appears in each service skill.

| Tier | Label | Rule |
|------|-------|------|
| Safe | 🟢 SAFE | Proceed freely |
| Sensitive | 🔵 SENSITIVE | State intent before proceeding |
| Destructive | ⚠️ DESTRUCTIVE | Require explicit user confirmation before calling |

### Confirmation gate — required before every ⚠️ DESTRUCTIVE call

```
1. Describe exactly what will change:
   "This will permanently [delete/stop/modify] [X]."
2. Ask: "Confirm? (yes / no)"
3. Wait for explicit 'yes'. Any other response → abort.
4. On abort: tell the user what was NOT done and why.
```

### Intent declaration — required before every 🔵 SENSITIVE call

```
State your intent before proceeding:
"I'm going to [read/access] [X], which may contain [passwords/tokens/script source/private data]."
Then proceed — no confirmation needed, but the action must be explicitly announced.
```

---

## Error Handling

```python
from tools.synology_client import (
    SynologyClientError,
    SynologyAPIError,
    SynologyAuthError,
    SynologySSHError,
    SynologySSHNotAvailable,
)

try:
    result = fs.list_dir("/volume1/data")
except SynologyAuthError as e:
    print("Missing credentials:", e)
except SynologyAPIError as e:
    print(f"API error {e.error_code} in {e.context}")
    # See references/dsm-api-gaps.md for error code meanings
except SynologySSHNotAvailable:
    print("Install paramiko: pip install paramiko")
```

Common error codes:

| Code | Meaning |
|------|---------|
| 119 | Session expired — re-instantiate |
| 105 | Permission denied |
| 900 | File/folder not found (FileStation) |
| 901 | File already exists |
| 800 | Task not found (DownloadStation) |

Full list: [`references/dsm-api-gaps.md`](references/dsm-api-gaps.md)

---

## SSH Availability

SSH requires both `paramiko` installed **and** a CLI execution environment.
Always check both flags before attempting SSH:

```python
from tools.synology_client import SSH_AVAILABLE, RUNNING_IN_CLI, get_ssh

if not RUNNING_IN_CLI:
    raise RuntimeError(
        "SSH is only available in Claude Code CLI environments. "
        "The web UI does not have access to a local network or filesystem."
    )
if not SSH_AVAILABLE:
    raise RuntimeError("paramiko not installed — run: pip install paramiko")

with get_ssh() as ssh:
    stdout, stderr, exit_code = ssh.run("hostname")
```

| Flag | Meaning |
|------|---------|
| `RUNNING_IN_CLI` | `True` when `CLAUDECODE=1` is set (Claude Code CLI bash environment) |
| `SSH_AVAILABLE` | `True` when `paramiko` is importable |

Both must be `True` for SSH to work. `RUNNING_IN_CLI` is `False` in the web UI,
Claude hooks, and status-line commands even when paramiko is installed.
Do not silently fall back to SSH — always check both flags explicitly.

---

## Known Limitations

- No native Container Manager `restart` — wrapper does stop + 2s sleep + start
- API container logs truncated — use `SynologySSH.docker_logs()` for full output
- No `docker exec`, `pull`, or `build` via API — SSH only
- `create_script_task()` creates non-root tasks only (root tasks need separate token)
- Session is class-level: `logout()` on one invalidates all
- `cert_verify=False` hardcoded in factory functions

Full details: [`references/dsm-api-gaps.md`](references/dsm-api-gaps.md)

---

## Service Skills

Load the relevant skill for the operation you need:

| Skill | Operations |
|-------|-----------|
| `synology-filestation` | Browse, upload, download, search, share links |
| `synology-downloadstation` | Add tasks, list, pause/resume/delete |
| `synology-taskscheduler` | List, create, run, enable/disable, delete |
| `synology-container-manager` | Start/stop containers, SSH exec/pull/build |
