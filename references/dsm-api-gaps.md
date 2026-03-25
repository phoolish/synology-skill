# DSM API Gaps and Known Limitations

Reference for `tools/synology_client.py` and all `skills/` files.
When something doesn't work as expected, check this file first.

---

## DSM API Error Codes

### Authentication / Session (100-series)

| Code | Meaning | Resolution |
|------|---------|------------|
| 100 | Unknown error | Check DSM logs |
| 101 | Invalid parameter | Check method arguments |
| 102 | API does not exist | Package not installed or wrong API name |
| 103 | Method does not exist | Unsupported DSM version or wrong method |
| 105 | Permission denied | User lacks required DSM permissions |
| 106 | Session timeout | Re-instantiate (call factory function again) |
| 119 | Invalid session | Session expired (DSM default: 15 min); re-instantiate |
| 400 | No such account | Check SYNOLOGY_USER value |
| 401 | Account disabled | Re-enable account in DSM Control Panel |
| 403 | Permission denied (login) | Wrong password or account locked |

### FileStation (900-series)

| Code | Meaning | Resolution |
|------|---------|------------|
| 900 | No such file or folder | Check path format: /volume1/share/folder |
| 901 | File already exists | Use overwrite=True or rename first |
| 902 | Disk quota exceeded | Free up space or increase quota |
| 903 | No permission | Check share and folder permissions for the user |
| 908 | Failed to write / create | Check disk health and available space |
| 1800 | File too large | Upload in chunks or use alternative method |

### DownloadStation (800-series)

| Code | Meaning | Resolution |
|------|---------|------------|
| 800 | File does not exist | Task ID may be invalid or task was deleted |
| 801 | Invalid task action | Task is in wrong state (e.g., pause on finished) |
| 802 | Already exists | URL/torrent already queued |
| 900 | Unknown error | Check DownloadStation logs in DSM |

---

## Session Sharing

`synology-api` uses a **class-level shared session** via `BaseApi`:

- Instantiating `FileStation` and then `DownloadStation` in the same process shares auth.
- **Calling `logout()` on any instance invalidates all sessions** for all classes.
- You cannot authenticate as two different DSM users in the same process.
- On session expiry (error 119), re-call the factory function to get a fresh instance.
- DSM default session timeout: 15 minutes of inactivity.

---

## Container Manager API Gaps

### No native restart method
`SYNO.Docker.Container` has no restart endpoint. `SynologyContainerManager.restart()`
implements `stop()` + 2-second sleep + `start()`. This means:
- There is a brief window where the container is fully stopped.
- If `stop()` succeeds but `start()` fails, the container stays stopped.

### No `docker exec` equivalent
The DSM API has no way to run commands inside a running container.
**Use `SynologySSH.docker_exec()` instead.**

### No `docker pull` or `docker build`
Image management is not exposed via the DSM API.
**Use `SynologySSH.docker_pull()` and `SynologySSH.docker_build()` instead.**

### API logs are truncated
`ContainerManager.get_logs()` returns a limited log buffer.
**Use `SynologySSH.docker_logs()` for full output.**

### Container names vs IDs
DSM API methods use container **names** (not IDs). The name is what appears in the
Container Manager UI. Use `list_containers()` to look up names if uncertain.

### Project operations use UUIDs
`list_projects()` returns project objects with an `id` field (a UUID-like string).
Project-level operations (start/stop a compose project) require this ID, not the project name.

### Docker binary not in $PATH for SSH users
The docker binary location on DSM is:
```
/var/packages/ContainerManager/target/usr/bin/docker
```
This path is the default for `SynologySSH`. If docker commands via SSH return exit_code=127
(command not found), verify the path or set `SYNOLOGY_DOCKER_BIN` to the correct location.

---

## Task Scheduler Limitations

### Non-root tasks only (factory function)
`create_script_task()` creates tasks owned by the connected DSM user. Creating **root tasks**
requires a separate root token that the factory function does not handle. To create root tasks,
instantiate `TaskScheduler` directly and use the root token flow documented in the library source.

### `owner` parameter is a DSM username
The `owner` argument in TaskScheduler methods is the DSM username string (e.g., `"admin"`),
not a user ID. It must match the owner shown in `list_tasks()`. Getting this wrong causes
permission errors or task-not-found responses.

### Event triggers not supported
`SynologyTaskScheduler` wraps scheduled (time-based) tasks only. Event-triggered tasks
(e.g., "run when USB device connected") use `SYNO.Core.EventScheduler`, which is not
wrapped by `synology-api`. Use SSH + `synowebapi` for event triggers.

---

## FileStation Async Operations

The following FileStation operations are **asynchronous** — they start a background task
and require polling for completion:

| Operation | Start method | Poll method | Wrapper hides this? |
|-----------|-------------|-------------|---------------------|
| search | `search_start()` | `get_search_list()` | ✅ Yes (30s cap) |
| copy | `start_copy_move()` | `get_copy_move_status()` | ✅ Yes |
| move | `start_copy_move()` | `get_copy_move_status()` | ✅ Yes |
| delete | `delete_blocking_function()` | N/A | ✅ Synchronous |

The 30-second polling cap on `search()` is a safety limit. For large directories,
consider calling `search_start()` and polling manually.

---

## SSL / TLS

Factory functions use `secure=True, cert_verify=False`. This is intentional:
Synology NAS devices ship with self-signed certificates by default.

For environments with valid certificates (custom CA or Let's Encrypt via DDNS):
- Instantiate the library class directly with `cert_verify=True`.
- Factory functions do not expose this option.

---

## DSM Version Compatibility

`synology-api` v0.8.2 targets **DSM 7.x** (`dsm_version=7`).

- DSM 6.x users: instantiate library classes directly with `dsm_version=6`.
  Some API endpoints may not exist on DSM 6.x.
- DSM 7.2+ introduced Container Manager (replaces legacy Docker package).
  On DSM < 7.2, `docker_api.Docker` may not function.

---

## Avoid: `batch_request` / `request_multi_datas`

These methods are exposed by `BaseApi` but are underdocumented. Behavior is inconsistent
across DSM versions. Do not use them — make individual API calls instead.
