# FileStation API Reference

Reference for `SynologyFileStation` in `tools/synology_client.py`.

---

## Path Format

All paths use Unix format with the volume prefix:

```
/volume1/sharename/folder/file.txt
```

- Volume is typically `/volume1` (or `/volume2` on NAS with multiple volumes)
- Share name is the top-level shared folder name (visible in File Station UI)
- Symlinks are treated as files — their targets are not automatically resolved
- Shares themselves appear at: `/volume1/sharename` (no trailing slash)

---

## Method Reference

### `list_shares()`

Returns all shared folders visible to the authenticated user.

```python
result = fs.list_shares()
for share in result['data']['shares']:
    print(share['name'], share['path'])
    # share['path'] = "/volume1/sharename"
```

### `list_dir(path, offset=0, limit=100)`

Lists files and folders in a directory.

```python
result = fs.list_dir("/volume1/data")
for item in result['data']['files']:
    print(item['name'], item['path'], item['isdir'])
```

Pagination: use `offset` and `limit` for large directories. `result['data']['total']` gives
the total count. `limit=-1` is not supported — use 200 as a practical maximum.

### `file_info(paths: list[str])`

Get metadata (size, permissions, timestamps, type) for specific files or folders.

```python
result = fs.file_info(["/volume1/data/file.txt", "/volume1/data/folder"])
for item in result['data']['files']:
    print(item['name'], item['additional']['size'])
```

### `search(path, pattern, timeout_seconds=30)`

Search for files/folders matching a glob pattern. Wraps the async DSM search API.

```python
result = fs.search("/volume1/data", "*.log")
for item in result['data']['files']:
    print(item['path'])
```

The search is async in the DSM API. The wrapper polls until `finished=True` or
`timeout_seconds` elapses (default 30s). For large directories, increase the timeout:

```python
result = fs.search("/volume1/media", "*.mkv", timeout_seconds=120)
```

### `upload(local_path, remote_dir, overwrite=False)`

Upload a local file to a remote directory.

```python
fs.upload("/tmp/report.pdf", "/volume1/documents")
```

- `local_path`: absolute path on the machine running Claude Code
- `remote_dir`: directory path on the NAS (not including filename)
- Uses multipart upload — large files may take time proportional to network speed
- `overwrite=False` raises error 901 if file exists; set `overwrite=True` to replace

### `download(remote_path, dest_dir)` 🔵 SENSITIVE

Download a file. Returns raw bytes. Caller writes to `dest_dir`.

```python
data = fs.download("/volume1/documents/report.pdf", "/tmp")
with open("/tmp/report.pdf", "wb") as f:
    f.write(data)
```

### `create_dir(path)`

Create a new directory. `path` is the full path including the new directory name.

```python
fs.create_dir("/volume1/data/new-folder")
```

### `rename(path, new_name)`

Rename a file or folder. `new_name` is the name only (not a full path).

```python
fs.rename("/volume1/data/old-name.txt", "new-name.txt")
```

### `copy(source, dest_dir)`

Copy a file or folder. Wraps async API — polls until complete.

```python
fs.copy("/volume1/data/file.txt", "/volume1/backup")
# Result: /volume1/backup/file.txt
```

### `move(source, dest_dir)` ⚠️ DESTRUCTIVE

Move a file or folder. Removes from source location. Wraps async API.

```python
fs.move("/volume1/data/file.txt", "/volume1/archive")
```

### `delete(path)` ⚠️ DESTRUCTIVE

Permanently delete a file or folder. Uses `delete_blocking_function()` — synchronous.

```python
fs.delete("/volume1/data/old-file.txt")
```

Deletes recursively if `path` is a folder. There is no recycle bin — deletion is permanent.

### `create_share_link(path, expires_days=None, password=None)`

Create a public share link for a file.

```python
result = fs.create_share_link(
    "/volume1/media/photo.jpg",
    expires_days=7,
    password="secret123",
)
link_url = result['data']['links'][0]['url']
link_id  = result['data']['links'][0]['id']
```

`expires_days=None` creates a permanent link. `password=None` creates an unprotected link.

### `list_share_links()`

List all active share links.

```python
result = fs.list_share_links()
for link in result['data']['links']:
    print(link['id'], link['url'], link['has_password'])
```

### `delete_share_link(link_id)` ⚠️ DESTRUCTIVE

Delete a share link by ID. Anyone with the link URL loses access immediately.

---

## Async Operations: Copy / Move / Search

These DSM operations start a background task. The wrapper hides the polling:

```
Operation    start_method()         poll_method()              Poll interval
---------    --------------         -------------              ------------
search       search_start()         get_search_list()          0.5s (30s cap)
copy/move    start_copy_move()      get_copy_move_status()     0.5s (no cap)
```

If you need to search very large directories and hit the 30s cap, call the underlying API directly:

```python
fs_raw = fs._api
task = fs_raw.search_start(folder_path="/volume1/large", pattern="*.iso")
task_id = task['data']['taskid']
# poll manually with: fs_raw.get_search_list(task_id=task_id)
```

---

## Permissions

The connected DSM user (SYNOLOGY_USER) must have appropriate permissions:
- Read access to a shared folder to `list_dir`, `file_info`, `search`, `download`
- Read/Write access to upload, create, rename, copy, move, delete
- Shared folder permissions are set in DSM Control Panel → Shared Folder
- File-level permissions follow standard Unix rwxr-xr-x rules
