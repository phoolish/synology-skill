# DownloadStation API Reference

Reference for `SynologyDownloadStation` in `tools/synology_client.py`.

---

## Task Status State Machine

```
add_url()
    │
    ▼
waiting ──► downloading ──► finishing ──► finished
    │            │
    │            ├──► hash_checking ──► seeding
    │            │
    │            ├──► filehosting_waiting
    │            │
    │            └──► extracting ──► finished
    │
    ├──► paused (via pause())
    │        └──► downloading (via resume())
    │
    └──► error
```

**pause() is only valid** when task status is `downloading`.
**resume() is only valid** when task status is `paused`.
Calling pause/resume on tasks in other states returns error 801.

---

## Method Reference

### `list_tasks(offset=0, limit=100)`

List all download tasks with transfer details, file info, and metadata.

```python
result = ds.list_tasks()
for task in result['data']['tasks']:
    print(task['id'], task['title'], task['status'])
    print("  Downloaded:", task['additional']['transfer']['size_downloaded'])
    print("  Total size:", task['additional']['detail']['total_pieces'])
```

Key fields in each task object:
- `id`: task ID string (e.g., `"dbid_123"`)
- `title`: display name
- `status`: one of the state values above
- `type`: `"bt"` (BitTorrent), `"http"`, `"ftp"`, `"nzb"`, etc.
- `additional.transfer.speed_download`: current download speed in bytes/s
- `additional.transfer.size_downloaded`: bytes downloaded so far
- `additional.detail.destination`: save path on NAS
- `additional.file`: array of files within torrent (if applicable)

Pagination: use `offset` + `limit`. `result['data']['total']` gives the total count.
Maximum practical `limit` is 200 (undocumented cap).

### `task_info(task_id)`

Get detailed info for a single task. Same structure as a list_tasks entry.

```python
result = ds.task_info("dbid_123")
task = result['data']['tasks'][0]
```

### `add_url(url, destination="")`

Add a download task by URL.

```python
# HTTP/HTTPS
ds.add_url("https://example.com/file.zip")

# Magnet link
ds.add_url("magnet:?xt=urn:btih:abc123&dn=Example+File")

# Direct .torrent URL
ds.add_url("https://example.com/file.torrent")

# Specify destination folder on NAS
ds.add_url("https://example.com/file.zip", destination="/volume1/downloads/videos")
```

`destination=""` uses the default folder from `get_config()['data']['default_destination']`.

Supported protocols: HTTP, HTTPS, FTP, SFTP, magnet (BitTorrent), .torrent URLs.
NZB files require the DownloadStation NZB add-on package.
Local `.torrent` files cannot be uploaded directly via `add_url` — upload to FileStation first,
then reference the NAS path.

### `pause(task_id)` / `resume(task_id)`

```python
tasks = ds.list_tasks()
for task in tasks['data']['tasks']:
    if task['status'] == 'downloading':
        ds.pause(task['id'])
```

### `delete(task_id, force=False)` ⚠️ DESTRUCTIVE

```python
ds.delete("dbid_123")           # safe: only deletes if not actively downloading
ds.delete("dbid_123", force=True)  # force: deletes even if downloading
```

`force=False` (default) is safer — it prevents accidentally cancelling an active download.

### `get_config()`

Returns DownloadStation configuration:

```python
result = ds.get_config()
config = result['data']
print(config['default_destination'])   # default save path
print(config['max_download_rate'])     # speed limit in KB/s; 0 = unlimited
print(config['max_upload_rate'])       # speed limit in KB/s; 0 = unlimited
```

### `get_statistics()`

Returns aggregate transfer statistics:

```python
result = ds.get_statistics()
stats = result['data']
print(stats['speed_download'])   # current total download speed (bytes/s)
print(stats['speed_upload'])     # current total upload speed (bytes/s)
```

---

## Task ID Format

Task IDs are strings like `"dbid_123"` or `"httpdl_456"`. They are assigned by DSM and
are not sequential integers. Always retrieve IDs from `list_tasks()` — do not guess.

---

## BitTorrent Notes

- Magnet links: DSM resolves magnet links by contacting the DHT network.
  If the NAS has no internet access, magnet links may stall at `waiting`.
- Seeding: after download completes, torrent tasks enter `seeding` state.
  They remain seeding until you `pause()` or `delete()` them.
- File selection within a torrent is not exposed via `synology-api`. Use DSM UI to select files.
