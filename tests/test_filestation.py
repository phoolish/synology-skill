"""
Tests for SynologyFileStation.

Key cases:
- list_shares / list_dir / file_info: happy path and API error
- search: async polling loop (finished on 1st, 2nd, and Nth poll; timeout)
- upload / download: argument pass-through
- copy / move: polling loop, remove_src distinction
- delete: calls delete_blocking_function
- share links: create / list / delete
"""

import pytest
from unittest.mock import MagicMock
from tests.conftest import ok, err


@pytest.fixture()
def mock_fs():
    """
    Build a SynologyFileStation with _api replaced by a MagicMock.
    Bypasses __init__ (which would try to connect to the NAS).
    Yields (fs_instance, mock_api).
    """
    from tools.synology_client import SynologyFileStation
    mock_api = MagicMock()
    fs = SynologyFileStation.__new__(SynologyFileStation)
    fs._api = mock_api
    yield fs, mock_api


# ---------------------------------------------------------------------------
# list_shares
# ---------------------------------------------------------------------------

class TestListShares:
    def test_returns_shares(self, mock_fs):
        fs, api = mock_fs
        api.get_list_share.return_value = ok({"shares": [{"name": "data"}]})
        result = fs.list_shares()
        assert result["data"]["shares"][0]["name"] == "data"

    def test_raises_on_api_error(self, mock_fs):
        from tools.synology_client import SynologyAPIError
        fs, api = mock_fs
        api.get_list_share.return_value = err(105)
        with pytest.raises(SynologyAPIError) as exc:
            fs.list_shares()
        assert exc.value.error_code == 105


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------

class TestListDir:
    def test_passes_path_and_pagination(self, mock_fs):
        fs, api = mock_fs
        api.get_file_list.return_value = ok({"files": [], "total": 0})
        fs.list_dir("/volume1/data", offset=10, limit=50)
        api.get_file_list.assert_called_once_with(
            folder_path="/volume1/data", offset=10, limit=50
        )

    def test_default_pagination(self, mock_fs):
        fs, api = mock_fs
        api.get_file_list.return_value = ok({"files": [], "total": 0})
        fs.list_dir("/volume1/data")
        api.get_file_list.assert_called_once_with(
            folder_path="/volume1/data", offset=0, limit=100
        )


# ---------------------------------------------------------------------------
# search (async polling)
# ---------------------------------------------------------------------------

class TestSearch:
    def _start_ok(self):
        return ok({"taskid": "task_abc"})

    def _poll(self, finished: bool, files=None):
        return ok({"finished": finished, "files": files or []})

    def test_returns_result_when_finished_on_first_poll(self, mock_fs, mocker):
        fs, api = mock_fs
        mocker.patch("time.sleep")  # don't actually sleep
        api.search_start.return_value = self._start_ok()
        api.get_search_list.return_value = self._poll(
            finished=True, files=[{"path": "/volume1/a.txt"}]
        )

        result = fs.search("/volume1", "*.txt")
        assert result["data"]["files"][0]["path"] == "/volume1/a.txt"
        api.get_search_list.assert_called_once()

    def test_polls_until_finished(self, mock_fs, mocker):
        fs, api = mock_fs
        mocker.patch("time.sleep")
        api.search_start.return_value = self._start_ok()
        # First two polls not finished, third is finished
        api.get_search_list.side_effect = [
            self._poll(finished=False),
            self._poll(finished=False),
            self._poll(finished=True, files=[{"path": "/volume1/b.mkv"}]),
        ]

        result = fs.search("/volume1/media", "*.mkv")
        assert api.get_search_list.call_count == 3
        assert result["data"]["files"][0]["path"] == "/volume1/b.mkv"

    def test_raises_on_timeout(self, mock_fs, mocker):
        from tools.synology_client import SynologyAPIError
        fs, api = mock_fs
        mocker.patch("time.sleep")
        mocker.patch("time.time", side_effect=[0, 0, 999])  # instant timeout
        api.search_start.return_value = self._start_ok()
        api.get_search_list.return_value = self._poll(finished=False)

        with pytest.raises(SynologyAPIError) as exc:
            fs.search("/volume1", "*.iso", timeout_seconds=1)
        assert exc.value.context == "search_timeout"

    def test_raises_on_search_start_error(self, mock_fs, mocker):
        from tools.synology_client import SynologyAPIError
        fs, api = mock_fs
        mocker.patch("time.sleep")
        api.search_start.return_value = err(900)

        with pytest.raises(SynologyAPIError) as exc:
            fs.search("/volume1", "*.txt")
        assert exc.value.error_code == 900


# ---------------------------------------------------------------------------
# upload / download
# ---------------------------------------------------------------------------

class TestUploadDownload:
    def test_upload_passes_args(self, mock_fs):
        fs, api = mock_fs
        api.upload_file.return_value = ok({})
        fs.upload("/tmp/file.pdf", "/volume1/docs")
        api.upload_file.assert_called_once_with(
            dest_folder_path="/volume1/docs",
            file_path="/tmp/file.pdf",
            overwrite=False,
        )

    def test_upload_overwrite_flag(self, mock_fs):
        fs, api = mock_fs
        api.upload_file.return_value = ok({})
        fs.upload("/tmp/file.pdf", "/volume1/docs", overwrite=True)
        api.upload_file.assert_called_once_with(
            dest_folder_path="/volume1/docs",
            file_path="/tmp/file.pdf",
            overwrite=True,
        )

    def test_download_returns_bytes(self, mock_fs):
        fs, api = mock_fs
        api.get_file.return_value = b"filecontent"
        result = fs.download("/volume1/docs/file.pdf", "/tmp")
        assert result == b"filecontent"
        api.get_file.assert_called_once_with(
            path="/volume1/docs/file.pdf", mode="download"
        )


# ---------------------------------------------------------------------------
# create_dir / rename
# ---------------------------------------------------------------------------

class TestCreateDirRename:
    def test_create_dir_splits_path(self, mock_fs):
        fs, api = mock_fs
        api.create_folder.return_value = ok({})
        fs.create_dir("/volume1/data/new-folder")
        api.create_folder.assert_called_once_with(
            folder_path="/volume1/data", name="new-folder"
        )

    def test_rename_passes_args(self, mock_fs):
        fs, api = mock_fs
        api.rename_entry.return_value = ok({})
        fs.rename("/volume1/data/old.txt", "new.txt")
        api.rename_entry.assert_called_once_with(
            path="/volume1/data/old.txt", name="new.txt"
        )


# ---------------------------------------------------------------------------
# copy / move (polling loop)
# ---------------------------------------------------------------------------

class TestCopyMove:
    def _start(self):
        return ok({"taskid": "copy_task_1"})

    def _status(self, finished: bool):
        return ok({"finished": finished})

    def test_copy_uses_remove_src_false(self, mock_fs, mocker):
        fs, api = mock_fs
        mocker.patch("time.sleep")
        api.start_copy_move.return_value = self._start()
        api.get_copy_move_status.return_value = self._status(finished=True)

        fs.copy("/volume1/a.txt", "/volume1/backup")
        api.start_copy_move.assert_called_once_with(
            path="/volume1/a.txt",
            dest_folder_path="/volume1/backup",
            overwrite=False,
            remove_src=False,
        )

    def test_move_uses_remove_src_true(self, mock_fs, mocker):
        fs, api = mock_fs
        mocker.patch("time.sleep")
        api.start_copy_move.return_value = self._start()
        api.get_copy_move_status.return_value = self._status(finished=True)

        fs.move("/volume1/a.txt", "/volume1/archive")
        api.start_copy_move.assert_called_once_with(
            path="/volume1/a.txt",
            dest_folder_path="/volume1/archive",
            overwrite=False,
            remove_src=True,
        )

    def test_copy_polls_until_finished(self, mock_fs, mocker):
        fs, api = mock_fs
        mocker.patch("time.sleep")
        api.start_copy_move.return_value = self._start()
        api.get_copy_move_status.side_effect = [
            self._status(finished=False),
            self._status(finished=False),
            self._status(finished=True),
        ]
        fs.copy("/volume1/a.txt", "/volume1/backup")
        assert api.get_copy_move_status.call_count == 3


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_uses_blocking_delete(self, mock_fs):
        fs, api = mock_fs
        api.delete_blocking_function.return_value = ok({})
        fs.delete("/volume1/data/old.txt")
        api.delete_blocking_function.assert_called_once_with(
            path="/volume1/data/old.txt"
        )

    def test_raises_on_not_found(self, mock_fs):
        from tools.synology_client import SynologyAPIError
        fs, api = mock_fs
        api.delete_blocking_function.return_value = err(900)
        with pytest.raises(SynologyAPIError) as exc:
            fs.delete("/volume1/data/ghost.txt")
        assert exc.value.error_code == 900


# ---------------------------------------------------------------------------
# Share links
# ---------------------------------------------------------------------------

class TestShareLinks:
    def test_create_link_no_options(self, mock_fs):
        fs, api = mock_fs
        api.sharing_create_link.return_value = ok(
            {"links": [{"id": "abc", "url": "https://nas/abc"}]}
        )
        result = fs.create_share_link("/volume1/photo.jpg")
        api.sharing_create_link.assert_called_once_with(
            path="/volume1/photo.jpg"
        )
        assert result["data"]["links"][0]["id"] == "abc"

    def test_create_link_with_expiry_and_password(self, mock_fs):
        fs, api = mock_fs
        api.sharing_create_link.return_value = ok({"links": [{"id": "xyz"}]})
        fs.create_share_link(
            "/volume1/doc.pdf", expires_days=7, password="s3cr3t"
        )
        api.sharing_create_link.assert_called_once_with(
            path="/volume1/doc.pdf",
            date_expired=7,
            link_password="s3cr3t",
        )

    def test_list_links(self, mock_fs):
        fs, api = mock_fs
        api.sharing_get_info.return_value = ok({"links": []})
        fs.list_share_links()
        api.sharing_get_info.assert_called_once()

    def test_delete_link(self, mock_fs):
        fs, api = mock_fs
        api.sharing_delete_link.return_value = ok({})
        fs.delete_share_link("abc123")
        api.sharing_delete_link.assert_called_once_with(link_id="abc123")
