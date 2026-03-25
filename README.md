# Synology NAS Skill

Claude Code skill and Python helper for interacting with a Synology NAS via DSM API and SSH.

## Prerequisites

- Python 3.10+
- Synology NAS running DSM 7.x
- DSM user account (no 2FA)
- HTTPS access to the NAS (port 5001 by default)

## Installation

```bash
pip install synology-api          # Required
pip install paramiko               # Optional — enables SSH operations
```

## Directory Structure

```
synology-skill/
├── SKILL.md                              # Base Claude Code skill (auth, patterns, authorization)
├── README.md                             # This file
├── skills/
│   ├── synology-filestation.md           # FileStation skill
│   ├── synology-downloadstation.md       # DownloadStation skill
│   ├── synology-taskscheduler.md         # Task Scheduler skill
│   └── synology-container-manager.md    # Container Manager + SSH skill
├── tools/
│   └── synology_client.py                # Importable Python helper
└── references/
    ├── dsm-api-gaps.md                   # API limitations and error codes
    ├── filestation-api.md
    ├── downloadstation-api.md
    ├── taskscheduler-api.md
    └── container-manager-api.md
```

## DSM Configuration

### 1. Enable HTTPS

DSM Control Panel → Network → DSM Settings → Automatically redirect HTTP connections to HTTPS.

Default HTTPS port: 5001. Note the port — this is `SYNOLOGY_PORT`.

### 2. Create a Dedicated User

Recommended: create a dedicated user rather than using the admin account.

DSM Control Panel → User & Group → Create user.

Assign the minimum permissions needed for your use case (see Permissions section below).

### 3. Enable SSH (optional — required for Container Manager exec/pull/build)

DSM Control Panel → Terminal & SNMP → Terminal → Enable SSH service.

Default SSH port: 22. This is `SYNOLOGY_SSH_PORT` — **different from `SYNOLOGY_PORT`**.

## Environment Variables

```bash
# Required
export SYNOLOGY_HOST=192.168.1.100        # NAS hostname or IP
export SYNOLOGY_PORT=5001                  # DSM HTTPS port
export SYNOLOGY_USER=myuser                # DSM username
export SYNOLOGY_PASSWORD=mypassword        # DSM password

# Optional
export SYNOLOGY_SSH_KEY_PATH=~/.ssh/synology_ed25519  # SSH key (preferred over password)
export SYNOLOGY_SSH_PORT=22                            # SSH port (default: 22)
export SYNOLOGY_DOCKER_BIN=/var/packages/ContainerManager/target/usr/bin/docker
```

Add to `~/.zshrc`, `~/.bashrc`, or your project's `.env` file (never commit `.env` to git).

## Quick Connectivity Test

```bash
# Test DSM API connection
python -c "
from tools.synology_client import get_filestation, SSH_AVAILABLE
fs = get_filestation()
result = fs.list_shares()
print('Shares:', [s['name'] for s in result['data']['shares']])
print('SSH available:', SSH_AVAILABLE)
"
```

Expected output:
```
Shares: ['data', 'media', 'docker']
SSH available: True
```

## Minimum DSM Permissions

Configure per user in: DSM Control Panel → User & Group → Edit → Permissions tab.

| Module | Required Permission |
|--------|-------------------|
| FileStation | Shared folder read/write access as needed |
| DownloadStation | DownloadStation application permission |
| Task Scheduler | Read-only: any user; Create/Delete: admin or task owner |
| Container Manager | Docker application permission (or admin for SSH operations) |

For SSH operations, the user must have SSH login enabled. Root-equivalent access may be required
for `docker exec` and `docker build` — consider using `sudo` or adding the user to the `docker` group.

## Deploying Skills

Copy or symlink each skill to your Claude Code skills directory:

```bash
SKILLS_DIR=~/.claude/skills

mkdir -p "$SKILLS_DIR/synology-nas"
mkdir -p "$SKILLS_DIR/synology-filestation"
mkdir -p "$SKILLS_DIR/synology-downloadstation"
mkdir -p "$SKILLS_DIR/synology-taskscheduler"
mkdir -p "$SKILLS_DIR/synology-container-manager"

cp SKILL.md "$SKILLS_DIR/synology-nas/SKILL.md"
cp skills/synology-filestation.md "$SKILLS_DIR/synology-filestation/SKILL.md"
cp skills/synology-downloadstation.md "$SKILLS_DIR/synology-downloadstation/SKILL.md"
cp skills/synology-taskscheduler.md "$SKILLS_DIR/synology-taskscheduler/SKILL.md"
cp skills/synology-container-manager.md "$SKILLS_DIR/synology-container-manager/SKILL.md"
```

After deployment, each skill is independently invokable in Claude Code.

## Known Limitations

See [`references/dsm-api-gaps.md`](references/dsm-api-gaps.md) for the full list. Key points:

- **No native container restart** — wrapper does stop + 2s sleep + start
- **Container logs truncated via API** — use `SynologySSH.docker_logs()` for full output
- **No `docker exec`, `pull`, or `build` via API** — SSH only
- **Session is class-level** — `logout()` on any instance invalidates all
- **SSL** — `cert_verify=False` hardcoded in factory functions (fine for self-signed certs)
- **DSM 7.x only** — factory functions use `dsm_version=7`; DSM 6.x needs direct instantiation
- **Task Scheduler non-root only** via factory function — root tasks need separate token flow

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `SynologyAuthError: SYNOLOGY_HOST is not set` | Missing env var | Set all required env vars |
| API error 119 | Session expired (15 min default) | Call factory function again |
| API error 105 | Permission denied | Check user permissions in DSM |
| `SynologySSHNotAvailable` | paramiko not installed | `pip install paramiko` |
| SSH docker exit_code 127 | Docker binary not in PATH | Set `SYNOLOGY_DOCKER_BIN` |
| SSL error | Custom CA cert | Instantiate library directly with `cert_verify=True` |
