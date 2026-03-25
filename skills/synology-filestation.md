---
name: synology-filestation
description: Use when browsing, uploading, downloading, searching, or managing share links on a Synology NAS FileStation.
---

# Synology FileStation

Prerequisites: ensure env vars from `synology-nas` (SKILL.md) are set.
Authorization: follow the tier model defined in SKILL.md (🟢 SAFE / 🔵 SENSITIVE / ⚠️ DESTRUCTIVE).

```python
from tools.synology_client import get_filestation
fs = get_filestation()
```

Full reference: [`references/filestation-api.md`](../references/filestation-api.md)

---

## Path Format

All paths use Unix format: `/volume1/sharename/folder/file.txt`
Share root: `/volume1/sharename` (no trailing slash).

---

## Methods

### `list_shares()` — 🟢 SAFE
List all shared folders visible to the user.

```python
result = fs.list_shares()
for share in result['data']['shares']:
    print(share['name'], share['path'])
```

### `list_dir(path, offset=0, limit=100)` — 🟢 SAFE
List files and folders in a directory.

```python
result = fs.list_dir("/volume1/data")
for item in result['data']['files']:
    print(item['name'], item['isdir'])
```

Pagination: `result['data']['total']` is the total count. Max practical `limit` is 200.

### `file_info(paths: list[str])` — 🟢 SAFE
Get metadata for one or more files/folders.

```python
result = fs.file_info(["/volume1/data/file.txt"])
item = result['data']['files'][0]
print(item['additional']['size'])
```

### `search(path, pattern, timeout_seconds=30)` — 🟢 SAFE
Search for files matching a glob pattern. Wraps async API with polling.

```python
result = fs.search("/volume1/media", "*.mkv")
for item in result['data']['files']:
    print(item['path'])
```

Increase `timeout_seconds` for large directories. See [`references/filestation-api.md`](../references/filestation-api.md) for manual polling.

### `upload(local_path, remote_dir, overwrite=False)` — 🟢 SAFE
Upload a local file to a remote directory.

```python
fs.upload("/tmp/report.pdf", "/volume1/documents")
fs.upload("/tmp/report.pdf", "/volume1/documents", overwrite=True)
```

`local_path`: absolute path on the machine running Claude Code, not on the NAS.

### `download(remote_path, dest_dir)` — 🔵 SENSITIVE
Download a file. Returns raw bytes.

🔵 **Intent declaration required** before calling:
"I'm going to download `[remote_path]`, which may contain private data."

```python
data = fs.download("/volume1/documents/report.pdf", "/tmp")
with open("/tmp/report.pdf", "wb") as f:
    f.write(data)
```

### `create_dir(path)` — 🟢 SAFE
Create a new directory. `path` includes the new directory name.

```python
fs.create_dir("/volume1/data/new-folder")
```

### `rename(path, new_name)` — 🟢 SAFE
Rename a file or folder. `new_name` is the name only, not a full path.

```python
fs.rename("/volume1/data/old.txt", "new.txt")
```

### `copy(source, dest_dir)` — 🟢 SAFE
Copy a file or folder. Polls until complete.

```python
fs.copy("/volume1/data/file.txt", "/volume1/backup")
```

### `move(source, dest_dir)` — ⚠️ DESTRUCTIVE
Move a file or folder. Removes from source. Polls until complete.

⚠️ **Confirmation gate required** before calling:
1. "This will move `[source]` to `[dest_dir]`, removing it from its current location."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
fs.move("/volume1/data/file.txt", "/volume1/archive")
```

### `delete(path)` — ⚠️ DESTRUCTIVE
Permanently delete a file or folder. Deletes recursively if a folder. **Irreversible.**

⚠️ **Confirmation gate required** before calling:
1. "This will permanently delete `[path]` from the NAS. There is no recycle bin."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
fs.delete("/volume1/data/old-file.txt")
```

### `create_share_link(path, expires_days=None, password=None)` — 🟢 SAFE
Create a public share link.

```python
result = fs.create_share_link("/volume1/photos/trip.jpg", expires_days=7)
url = result['data']['links'][0]['url']
link_id = result['data']['links'][0]['id']
```

### `list_share_links()` — 🟢 SAFE
List all active share links.

```python
result = fs.list_share_links()
for link in result['data']['links']:
    print(link['id'], link['url'], link['has_password'])
```

### `delete_share_link(link_id)` — ⚠️ DESTRUCTIVE
Delete a share link. Anyone with the URL loses access immediately.

⚠️ **Confirmation gate required** before calling:
1. "This will permanently delete share link `[link_id]`. Anyone with the URL will lose access."
2. Ask: "Confirm? (yes / no)" — wait for explicit 'yes', otherwise abort.

```python
fs.delete_share_link("Abc123XYZ")
```
