---
name: synology-container-manager
description: Use when listing, starting, stopping, or restarting Docker containers on a Synology NAS, or when running exec, pull, build, or inspect via SSH.
---

# Synology Container Manager

Prerequisites: ensure env vars from `synology-nas` (SKILL.md) are set.
Authorization: follow the tier model defined in SKILL.md (🟢 SAFE / 🔵 SENSITIVE / ⚠️ DESTRUCTIVE).

```python
from tools.synology_client import get_container_manager, get_ssh, SSH_AVAILABLE
cm = get_container_manager()
```

Full reference: [`references/container-manager-api.md`](../references/container-manager-api.md)

---

## API vs SSH — Which to Use

| Need | Use |
|------|-----|
| List containers, images, projects | `cm` (API) |
| Start a container | `cm.start()` (API) |
| Stop / restart a container | `cm.stop()` / `cm.restart()` (API) ⚠️ |
| Run a command inside a container | `ssh.docker_exec()` ⚠️ |
| Pull an image | `ssh.docker_pull()` ⚠️ |
| Build an image | `ssh.docker_build()` ⚠️ |
| Full container logs | `ssh.docker_logs()` 🔵 |
| Container config / env vars | `ssh.docker_inspect()` 🔵 |

**SSH requires paramiko.** Always check availability before using SSH operations:

```python
if not SSH_AVAILABLE:
    raise RuntimeError("Install paramiko: pip install paramiko")
```

SSH must also be enabled on the NAS: DSM Control Panel → Terminal & SNMP → Enable SSH service.

---

## DSM API Methods

### `list_containers()` — 🟢 SAFE
List all containers (running and stopped).

```python
result = cm.list_containers()
for c in result['data']:
    print(c['name'], c['status'], c['image'])
```

Status values: `running`, `stopped`, `exited`, `paused`, `restarting`, `dead`

### `container_stats()` — 🟢 SAFE
Get live CPU/memory usage for all running containers.

```python
result = cm.container_stats()
```

### `list_images()` — 🟢 SAFE
List all downloaded images.

```python
result = cm.list_images()
```

### `list_projects()` — 🟢 SAFE
List Docker Compose projects.

```python
result = cm.list_projects()
for p in result['data']:
    print(p['id'], p['name'], p['status'])
    # Use p['id'] (UUID) for project operations — not the name
```

### `get_logs(container_name)` — 🔵 SENSITIVE
Get container logs via DSM API. **Logs are often truncated.** Use `ssh.docker_logs()` for full output.

🔵 **Intent declaration required** before calling:
"I'm going to read logs for container `[container_name]`, which may contain passwords, tokens, or sensitive output."

```python
result = cm.get_logs("plex")
```

### `start(container_name)` — 🟢 SAFE
Start a stopped container.

```python
cm.start("plex")
```

### `stop(container_name)` — ⚠️ DESTRUCTIVE
Stop a running container. Interrupts the service.

⚠️ **Confirmation gate required** before calling:
1. "This will stop container `[container_name]`, interrupting its service."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
cm.stop("plex")
```

### `restart(container_name)` — ⚠️ DESTRUCTIVE
Restart a container (stop + 2s sleep + start). Causes service interruption.

⚠️ **Confirmation gate required** before calling:
1. "This will restart container `[container_name]`, causing a brief service interruption."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
cm.restart("plex")
```

Note: No native DSM API restart method. If `stop()` succeeds but `start()` fails,
the container stays stopped. Check status with `list_containers()` after restart.

---

## SSH Methods

All SSH methods require `SSH_AVAILABLE == True` and an open connection.

```python
if not SSH_AVAILABLE:
    raise RuntimeError("Install paramiko: pip install paramiko")

with get_ssh() as ssh:
    stdout, stderr, exit_code = ssh.docker_exec("plex", "ls /config")
    if exit_code != 0:
        print("Error:", stderr)
```

`run()` does **not** raise on non-zero exit codes — always check `exit_code`.
If docker commands return `exit_code=127` (command not found), the docker binary path is wrong.
Set `SYNOLOGY_DOCKER_BIN` to the correct path. See [`references/container-manager-api.md`](../references/container-manager-api.md).

### `docker_exec(container, command)` — ⚠️ DESTRUCTIVE
Run a command inside a container.

⚠️ **Confirmation gate required** before calling:
1. "This will run `[command]` inside container `[container]`."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
with get_ssh() as ssh:
    stdout, stderr, code = ssh.docker_exec("plex", "ls /config")
```

### `docker_pull(image)` — ⚠️ DESTRUCTIVE
Pull an image from a registry. Modifies the local image store.

⚠️ **Confirmation gate required** before calling:
1. "This will pull image `[image]` onto the NAS."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
with get_ssh() as ssh:
    stdout, stderr, code = ssh.docker_pull("plexinc/pms-docker:latest")
    print(stdout)
```

### `docker_build(context_path, tag, dockerfile=None)` — ⚠️ DESTRUCTIVE
Build an image from a path on the NAS.

⚠️ **Confirmation gate required** before calling:
1. "This will build image `[tag]` from `[context_path]` on the NAS."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

`context_path`: absolute path **on the NAS filesystem**, not on the local machine.

```python
with get_ssh() as ssh:
    stdout, stderr, code = ssh.docker_build("/volume1/docker/myapp", "myapp:latest")
```

### `docker_logs(container, tail=100)` — 🔵 SENSITIVE
Get full container logs via docker CLI. Prefer this over `cm.get_logs()`.

🔵 **Intent declaration required** before calling:
"I'm going to read logs for container `[container]`, which may contain sensitive output."

```python
with get_ssh() as ssh:
    stdout, stderr, code = ssh.docker_logs("plex", tail=200)
    print(stdout)
```

### `docker_inspect(container)` — 🔵 SENSITIVE
Get full container configuration including environment variables.

🔵 **Intent declaration required** before calling:
"I'm going to inspect container `[container]`. The output includes environment variables that may contain credentials."

```python
with get_ssh() as ssh:
    stdout, stderr, code = ssh.docker_inspect("plex")
    import json
    config = json.loads(stdout)
```

### `run(command)` — ⚠️ DESTRUCTIVE
Run an arbitrary shell command on the NAS.

⚠️ **Confirmation gate required** before calling:
1. "This will run shell command `[command]` on the NAS."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
with get_ssh() as ssh:
    stdout, stderr, code = ssh.run("df -h")
```
