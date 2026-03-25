"""
Tests for SynologyDownloadStation.

Key cases:
- list_tasks: passes offset/limit/additional_param
- task_info: passes task_id
- add_url: passes url and destination
- pause / resume: action string passed correctly
- delete: passes task_id and force flag; raises on error
- get_config / get_statistics: happy path
"""

import pytest
from unittest.mock import MagicMock
from tests.conftest import ok, err


@pytest.fixture()
def mock_ds():
    """
    Build a SynologyDownloadStation with _api replaced by a MagicMock.
    Bypasses __init__ (which would try to connect to the NAS).
    Yields (ds_instance, mock_api).
    """
    from tools.synology_client import SynologyDownloadStation
    mock_api = MagicMock()
    ds = SynologyDownloadStation.__new__(SynologyDownloadStation)
    ds._api = mock_api
    yield ds, mock_api


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------

class TestListTasks:
    def test_passes_default_pagination(self, mock_ds):
        ds, api = mock_ds
        api.tasks_list.return_value = ok({"tasks": [], "total": 0})
        ds.list_tasks()
        api.tasks_list.assert_called_once_with(
            offset=0,
            limit=100,
            additional_param="transfer,detail,file",
        )

    def test_passes_custom_pagination(self, mock_ds):
        ds, api = mock_ds
        api.tasks_list.return_value = ok({"tasks": [], "total": 0})
        ds.list_tasks(offset=20, limit=10)
        api.tasks_list.assert_called_once_with(
            offset=20,
            limit=10,
            additional_param="transfer,detail,file",
        )

    def test_returns_tasks(self, mock_ds):
        ds, api = mock_ds
        api.tasks_list.return_value = ok(
            {"tasks": [{"id": "dbid_abc", "status": "downloading"}]}
        )
        result = ds.list_tasks()
        assert result["data"]["tasks"][0]["id"] == "dbid_abc"

    def test_raises_on_error(self, mock_ds):
        from tools.synology_client import SynologyAPIError
        ds, api = mock_ds
        api.tasks_list.return_value = err(800)
        with pytest.raises(SynologyAPIError) as exc:
            ds.list_tasks()
        assert exc.value.error_code == 800


# ---------------------------------------------------------------------------
# task_info
# ---------------------------------------------------------------------------

class TestTaskInfo:
    def test_passes_task_id(self, mock_ds):
        ds, api = mock_ds
        api.tasks_info.return_value = ok({"tasks": [{"id": "dbid_xyz"}]})
        ds.task_info("dbid_xyz")
        api.tasks_info.assert_called_once_with(task_id="dbid_xyz")


# ---------------------------------------------------------------------------
# add_url
# ---------------------------------------------------------------------------

class TestAddUrl:
    def test_passes_url_and_destination(self, mock_ds):
        ds, api = mock_ds
        api.create_task.return_value = ok({})
        ds.add_url("https://example.com/file.zip", "/volume1/downloads")
        api.create_task.assert_called_once_with(
            url="https://example.com/file.zip",
            destination="/volume1/downloads",
        )

    def test_default_destination_is_empty_string(self, mock_ds):
        ds, api = mock_ds
        api.create_task.return_value = ok({})
        ds.add_url("magnet:?xt=urn:btih:abc123")
        api.create_task.assert_called_once_with(
            url="magnet:?xt=urn:btih:abc123",
            destination="",
        )


# ---------------------------------------------------------------------------
# pause / resume
# ---------------------------------------------------------------------------

class TestPauseResume:
    def test_pause_sends_pause_action(self, mock_ds):
        ds, api = mock_ds
        api.tasks_action.return_value = ok({})
        ds.pause("dbid_abc")
        api.tasks_action.assert_called_once_with(
            action="pause", task_id="dbid_abc"
        )

    def test_resume_sends_resume_action(self, mock_ds):
        ds, api = mock_ds
        api.tasks_action.return_value = ok({})
        ds.resume("dbid_abc")
        api.tasks_action.assert_called_once_with(
            action="resume", task_id="dbid_abc"
        )


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_passes_task_id(self, mock_ds):
        ds, api = mock_ds
        api.tasks_action.return_value = ok({})
        ds.delete("dbid_abc")
        api.tasks_action.assert_called_once_with(
            action="delete",
            task_id="dbid_abc",
            force_complete=False,
        )

    def test_delete_force_flag(self, mock_ds):
        ds, api = mock_ds
        api.tasks_action.return_value = ok({})
        ds.delete("dbid_abc", force=True)
        api.tasks_action.assert_called_once_with(
            action="delete",
            task_id="dbid_abc",
            force_complete=True,
        )

    def test_raises_on_error(self, mock_ds):
        from tools.synology_client import SynologyAPIError
        ds, api = mock_ds
        api.tasks_action.return_value = err(800)
        with pytest.raises(SynologyAPIError) as exc:
            ds.delete("dbid_abc")
        assert exc.value.error_code == 800


# ---------------------------------------------------------------------------
# get_config / get_statistics
# ---------------------------------------------------------------------------

class TestConfigAndStats:
    def test_get_config_returns_data(self, mock_ds):
        ds, api = mock_ds
        api.get_config.return_value = ok(
            {"default_destination": "/volume1/downloads"}
        )
        result = ds.get_config()
        assert result["data"]["default_destination"] == "/volume1/downloads"
        api.get_config.assert_called_once()

    def test_get_statistics_returns_data(self, mock_ds):
        ds, api = mock_ds
        api.get_statistic_info.return_value = ok({"speed_download": 1024})
        result = ds.get_statistics()
        assert result["data"]["speed_download"] == 1024
        api.get_statistic_info.assert_called_once()
