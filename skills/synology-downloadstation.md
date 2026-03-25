---
name: synology-downloadstation
description: Use when adding, listing, pausing, resuming, or deleting download tasks on a Synology NAS DownloadStation.
---

# Synology DownloadStation

Prerequisites: ensure env vars from `synology-nas` (SKILL.md) are set.
Authorization: follow the tier model defined in SKILL.md (🟢 SAFE / 🔵 SENSITIVE / ⚠️ DESTRUCTIVE).

```python
from tools.synology_client import get_downloadstation
ds = get_downloadstation()
```

Full reference: [`references/downloadstation-api.md`](../references/downloadstation-api.md)

---

## Task Status Values

`waiting` → `downloading` → `finishing` → `finished`
Also: `paused`, `hash_checking`, `seeding`, `filehosting_waiting`, `extracting`, `error`

`pause()` is only valid when status is `downloading`.
`resume()` is only valid when status is `paused`.

---

## Methods

### `list_tasks(offset=0, limit=100)` — 🟢 SAFE
List all download tasks with transfer details.

```python
result = ds.list_tasks()
for task in result['data']['tasks']:
    print(task['id'], task['title'], task['status'])
    print("  Speed:", task['additional']['transfer']['speed_download'], "B/s")
```

Task ID format: strings like `"dbid_123"` — retrieve from `list_tasks()`, never guess.
Pagination: `result['data']['total']` is the total count.

### `task_info(task_id)` — 🟢 SAFE
Get detailed info for a single task.

```python
result = ds.task_info("dbid_123")
task = result['data']['tasks'][0]
print(task['status'], task['additional']['detail']['destination'])
```

### `add_url(url, destination="")` — 🟢 SAFE
Add a download task by URL.

```python
# HTTP/HTTPS
ds.add_url("https://example.com/file.zip")

# Magnet link
ds.add_url("magnet:?xt=urn:btih:abc123&dn=Example")

# Direct .torrent URL
ds.add_url("https://example.com/release.torrent")

# Custom destination on NAS
ds.add_url("https://example.com/file.zip", destination="/volume1/downloads/videos")
```

`destination=""` uses the default folder from `get_config()['data']['default_destination']`.
Local `.torrent` files: upload to FileStation first, then reference the NAS path.

### `pause(task_id)` — 🟢 SAFE
Pause a downloading task.

```python
ds.pause("dbid_123")
```

### `resume(task_id)` — 🟢 SAFE
Resume a paused task.

```python
ds.resume("dbid_123")
```

### `delete(task_id, force=False)` — ⚠️ DESTRUCTIVE
Delete a download task and its metadata.

⚠️ **Confirmation gate required** before calling:
1. "This will delete download task `[task_id]` (`[title]`)."
   If force=True add: "The task will be cancelled even if actively downloading."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
ds.delete("dbid_123")            # safe: only if not downloading
ds.delete("dbid_123", force=True)  # cancel even if active
```

### `get_config()` — 🟢 SAFE
Get DownloadStation configuration.

```python
result = ds.get_config()
print(result['data']['default_destination'])  # default save path
print(result['data']['max_download_rate'])    # KB/s; 0 = unlimited
```

### `get_statistics()` — 🟢 SAFE
Get aggregate transfer statistics.

```python
result = ds.get_statistics()
print(result['data']['speed_download'], "B/s download")
print(result['data']['speed_upload'], "B/s upload")
```
