"""
Tests for SynologyTaskScheduler.

Key cases:
- list_tasks: sort params passed through
- get_task: correct params including real_owner and type
- get_task_results: passes task_id
- run_now / enable / disable / delete: owner params
- create_script_task: schedule dict unpacked correctly
- modify_script_task: kwargs forwarded
"""

import pytest
from unittest.mock import MagicMock
from tests.conftest import ok, err


@pytest.fixture()
def mock_ts():
    """
    Build a SynologyTaskScheduler with _api replaced by a MagicMock.
    Bypasses __init__ (which would try to connect to the NAS).
    Yields (ts_instance, mock_api).
    """
    from tools.synology_client import SynologyTaskScheduler
    mock_api = MagicMock()
    ts = SynologyTaskScheduler.__new__(SynologyTaskScheduler)
    ts._api = mock_api
    yield ts, mock_api


# ---------------------------------------------------------------------------
# list_tasks
# ---------------------------------------------------------------------------

class TestListTasks:
    def test_default_sort(self, mock_ts):
        ts, api = mock_ts
        api.get_task_list.return_value = ok({"tasks": []})
        ts.list_tasks()
        api.get_task_list.assert_called_once_with(
            sort_by="name", sort_direction="ASC"
        )

    def test_custom_sort(self, mock_ts):
        ts, api = mock_ts
        api.get_task_list.return_value = ok({"tasks": []})
        ts.list_tasks(sort_by="next_trigger_time", sort_direction="DESC")
        api.get_task_list.assert_called_once_with(
            sort_by="next_trigger_time", sort_direction="DESC"
        )

    def test_returns_tasks(self, mock_ts):
        ts, api = mock_ts
        api.get_task_list.return_value = ok(
            {"tasks": [{"id": 42, "name": "backup"}]}
        )
        result = ts.list_tasks()
        assert result["data"]["tasks"][0]["id"] == 42

    def test_raises_on_error(self, mock_ts):
        from tools.synology_client import SynologyAPIError
        ts, api = mock_ts
        api.get_task_list.return_value = err(119)
        with pytest.raises(SynologyAPIError) as exc:
            ts.list_tasks()
        assert exc.value.error_code == 119


# ---------------------------------------------------------------------------
# get_task
# ---------------------------------------------------------------------------

class TestGetTask:
    def test_passes_all_params(self, mock_ts):
        ts, api = mock_ts
        api.get_task_config.return_value = ok({"task": {}})
        ts.get_task(42, "admin")
        api.get_task_config.assert_called_once_with(
            task_id=42, real_owner="admin", type="script"
        )

    def test_custom_task_type(self, mock_ts):
        ts, api = mock_ts
        api.get_task_config.return_value = ok({"task": {}})
        ts.get_task(7, "user1", task_type="beep_control")
        api.get_task_config.assert_called_once_with(
            task_id=7, real_owner="user1", type="beep_control"
        )


# ---------------------------------------------------------------------------
# get_task_results
# ---------------------------------------------------------------------------

class TestGetTaskResults:
    def test_passes_task_id(self, mock_ts):
        ts, api = mock_ts
        api.get_task_results.return_value = ok([
            {"task_id": 42, "exit_code": 0},
        ])
        ts.get_task_results(42)
        api.get_task_results.assert_called_once_with(task_id=42)

    def test_returns_results(self, mock_ts):
        ts, api = mock_ts
        api.get_task_results.return_value = ok([
            {"task_id": 1, "exit_code": 0},
            {"task_id": 1, "exit_code": 1},
        ])
        result = ts.get_task_results(1)
        assert len(result["data"]) == 2
        assert result["data"][1]["exit_code"] == 1


# ---------------------------------------------------------------------------
# run_now
# ---------------------------------------------------------------------------

class TestRunNow:
    def test_passes_task_id_and_owner(self, mock_ts):
        ts, api = mock_ts
        api.task_run.return_value = ok({})
        ts.run_now(42, "admin")
        api.task_run.assert_called_once_with(task_id=42, real_owner="admin")

    def test_raises_on_error(self, mock_ts):
        from tools.synology_client import SynologyAPIError
        ts, api = mock_ts
        api.task_run.return_value = err(900)
        with pytest.raises(SynologyAPIError) as exc:
            ts.run_now(42, "admin")
        assert exc.value.error_code == 900


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------

class TestEnableDisable:
    def test_enable_passes_true(self, mock_ts):
        ts, api = mock_ts
        api.task_set_enable.return_value = ok({})
        ts.enable(42, "admin")
        api.task_set_enable.assert_called_once_with(
            task_id=42, real_owner="admin", enable=True
        )

    def test_disable_passes_false(self, mock_ts):
        ts, api = mock_ts
        api.task_set_enable.return_value = ok({})
        ts.disable(42, "admin")
        api.task_set_enable.assert_called_once_with(
            task_id=42, real_owner="admin", enable=False
        )


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_passes_task_id_and_owner(self, mock_ts):
        ts, api = mock_ts
        api.task_delete.return_value = ok({})
        ts.delete(42, "admin")
        api.task_delete.assert_called_once_with(task_id=42, real_owner="admin")

    def test_raises_on_error(self, mock_ts):
        from tools.synology_client import SynologyAPIError
        ts, api = mock_ts
        api.task_delete.return_value = err(119)
        with pytest.raises(SynologyAPIError):
            ts.delete(99, "admin")


# ---------------------------------------------------------------------------
# create_script_task
# ---------------------------------------------------------------------------

class TestCreateScriptTask:
    def _schedule(self):
        return {
            "run_frequently": True,
            "run_days": "1,2,3,4,5",
            "repeat": "daily",
            "start_time_h": 2,
            "start_time_m": 30,
            "same_day_repeat_h": 0,
            "same_day_repeat_m": 0,
            "same_day_repeat_until": None,
        }

    def test_schedule_unpacked_correctly(self, mock_ts):
        ts, api = mock_ts
        api.create_script_task.return_value = ok({})
        ts.create_script_task(
            name="nightly-backup",
            owner="admin",
            script="#!/bin/bash\nrsync -av /volume1/data /volume1/backup",
            schedule=self._schedule(),
        )
        api.create_script_task.assert_called_once_with(
            task_name="nightly-backup",
            owner="admin",
            script="#!/bin/bash\nrsync -av /volume1/data /volume1/backup",
            enable=True,
            run_frequently=True,
            run_days="1,2,3,4,5",
            repeat="daily",
            start_time_h=2,
            start_time_m=30,
            same_day_repeat_h=0,
            same_day_repeat_m=0,
            same_day_repeat_until=None,
            notify_email="",
            notify_only_on_error=False,
        )

    def test_defaults_filled_when_schedule_keys_missing(self, mock_ts):
        ts, api = mock_ts
        api.create_script_task.return_value = ok({})
        ts.create_script_task(
            name="minimal",
            owner="admin",
            script="echo hi",
            schedule={"run_frequently": False},
        )
        call_kwargs = api.create_script_task.call_args.kwargs
        assert call_kwargs["run_days"] == "0,1,2,3,4,5,6"
        assert call_kwargs["repeat"] == "daily"
        assert call_kwargs["start_time_h"] == 0
        assert call_kwargs["start_time_m"] == 0


# ---------------------------------------------------------------------------
# modify_script_task
# ---------------------------------------------------------------------------

class TestModifyScriptTask:
    def test_forwards_kwargs(self, mock_ts):
        ts, api = mock_ts
        api.modify_script_task.return_value = ok({})
        ts.modify_script_task(42, script="echo updated", enable=False)
        api.modify_script_task.assert_called_once_with(
            task_id=42, script="echo updated", enable=False
        )
