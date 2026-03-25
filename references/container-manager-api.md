# Container Manager API Reference

DSM API coverage and SSH fallback guidance for `SynologyContainerManager` and `SynologySSH`.

---

## API vs SSH Decision Matrix

| Operation | DSM API | SSH | Notes |
|-----------|---------|-----|-------|
| List containers | ✅ | — | `list_containers()` |
| Container stats | ✅ | — | `container_stats()` |
| List images | ✅ | — | `list_images()` |
| List projects | ✅ | — | `list_projects()` |
| Start container | ✅ | — | `start()` |
| Stop container | ✅ | — | `stop()` ⚠️ DESTRUCTIVE |
| Restart container | ⚠️ workaround | — | `restart()` = stop + sleep + start |
| Get logs (basic) | ✅ truncated | ✅ full | API: `get_logs()` / SSH: `docker_logs()` |
| Exec in container | ❌ | ✅ | `SynologySSH.docker_exec()` ⚠️ DESTRUCTIVE |
| Pull image | ❌ | ✅ | `SynologySSH.docker_pull()` ⚠️ DESTRUCTIVE |
| Build image | ❌ | ✅ | `SynologySSH.docker_build()` ⚠️ DESTRUCTIVE |
| Docker inspect | ❌ | ✅ | `SynologySSH.docker_inspect()` 🔵 SENSITIVE |
| Compose project ops | partial | ✅ | Project start/stop via API is limited |

**Rule of thumb:** If it's a read of the container list or a simple start/stop → use API.
If it requires running code or inspecting configuration → use SSH.

---

## Enabling SSH on DSM

SSH must be explicitly enabled before `SynologySSH` will work.

1. DSM Control Panel → **Terminal & SNMP** → Terminal tab
2. Enable: **Enable SSH service**
3. Set port (default 22)
4. Click Apply

Test: `ssh SYNOLOGY_USER@SYNOLOGY_HOST` from a terminal.

---

## SSH Key Authentication Setup

Preferred over password for automation. On the machine running Claude Code:

```bash
# Generate key (if you don't have one)
ssh-keygen -t ed25519 -f ~/.ssh/synology_ed25519

# Copy public key to NAS
ssh-copy-id -i ~/.ssh/synology_ed25519.pub -p 22 USER@NAS_HOST

# Or manually:
cat ~/.ssh/synology_ed25519.pub | ssh USER@NAS_HOST "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# Set env var
export SYNOLOGY_SSH_KEY_PATH=~/.ssh/synology_ed25519
```

On DSM, authorized_keys lives at `/var/services/homes/USERNAME/.ssh/authorized_keys`.
Permissions must be `600` on authorized_keys and `700` on `.ssh`.

---

## Docker Binary Path

The `docker` binary is installed by the Container Manager package, not system-wide:

```
/var/packages/ContainerManager/target/usr/bin/docker
```

This path is not in `$PATH` for standard SSH users. `SynologySSH` uses this path by default.

**If docker commands fail with exit_code=127 (command not found):**
1. Verify the path: `ssh USER@HOST "ls /var/packages/ContainerManager/target/usr/bin/docker"`
2. If different, set: `export SYNOLOGY_DOCKER_BIN=/path/to/docker`

**Alternative: add to PATH in SSH session**
```bash
export PATH="/var/packages/ContainerManager/target/usr/bin:$PATH"
```
This can be added to the NAS user's `~/.bashrc` or `~/.profile`.

---

## Container Names vs IDs

DSM API methods use **container names** (the name shown in Container Manager UI), not container IDs.

- `start("plex")` → starts the container named "plex"
- Container IDs (SHA256 hashes) are not accepted by the DSM API
- Use `list_containers()` to look up names if uncertain

SSH docker commands accept both names and IDs:
```python
ssh.docker_exec("plex", "ls /config")          # by name
ssh.docker_exec("a1b2c3d4e5f6", "ls /config")  # by ID
```

---

## Project Operations

Docker Compose projects in Container Manager use UUIDs as identifiers:

```python
cm = get_container_manager()
projects = cm.list_projects()
# projects['data'] is a list of project objects
# Each has: id (UUID), name, status, path
project_id = projects['data'][0]['id']  # use this, not the name
```

The Container Manager UI shows project names; the API requires the UUID `id` field.

---

## Container Object Schema

From `list_containers()['data']` (array of container objects):

```json
{
  "id": "a1b2c3...",
  "name": "plex",
  "status": "running",
  "image": "plexinc/pms-docker:latest",
  "ports": [{"host": 32400, "container": 32400, "type": "tcp"}],
  "created": 1700000000,
  "size": 12345678
}
```

Status values: `running`, `stopped`, `exited`, `paused`, `restarting`, `dead`

---

## SSH Port vs DSM Port

These are different:

| Env var | Default | Service |
|---------|---------|---------|
| `SYNOLOGY_PORT` | 5001 | DSM HTTPS API |
| `SYNOLOGY_SSH_PORT` | 22 | SSH |

A common mistake is trying to SSH to port 5001. Set `SYNOLOGY_SSH_PORT=22` (or your custom SSH port)
separately from `SYNOLOGY_PORT`.
