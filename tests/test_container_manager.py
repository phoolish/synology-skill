"""
Tests for SynologyContainerManager.

Key cases:
- list_containers / container_stats / list_images / list_projects: happy path
- get_logs: passes container_name
- start / stop: pass container_name to correct API method
- restart: calls stop() + sleep(2) + start() in order
"""

import pytest
from unittest.mock import MagicMock
from tests.conftest import ok, err


@pytest.fixture()
def mock_cm():
    """
    Build a SynologyContainerManager with _api replaced by a MagicMock.
    Bypasses __init__ (which would try to connect to the NAS).
    Yields (cm_instance, mock_api).
    """
    from tools.synology_client import SynologyContainerManager
    mock_api = MagicMock()
    cm = SynologyContainerManager.__new__(SynologyContainerManager)
    cm._api = mock_api
    yield cm, mock_api


# ---------------------------------------------------------------------------
# list_containers
# ---------------------------------------------------------------------------

class TestListContainers:
    def test_returns_containers(self, mock_cm):
        cm, api = mock_cm
        api.containers.return_value = ok(
            [{"name": "plex", "status": "running"}]
        )
        result = cm.list_containers()
        assert result["data"][0]["name"] == "plex"
        api.containers.assert_called_once()

    def test_raises_on_error(self, mock_cm):
        from tools.synology_client import SynologyAPIError
        cm, api = mock_cm
        api.containers.return_value = err(900)
        with pytest.raises(SynologyAPIError) as exc:
            cm.list_containers()
        assert exc.value.error_code == 900


# ---------------------------------------------------------------------------
# container_stats
# ---------------------------------------------------------------------------

class TestContainerStats:
    def test_calls_docker_stats(self, mock_cm):
        cm, api = mock_cm
        api.docker_stats.return_value = ok(
            [{"name": "plex", "cpu_percent": 5.2}]
        )
        result = cm.container_stats()
        assert result["data"][0]["cpu_percent"] == 5.2
        api.docker_stats.assert_called_once()


# ---------------------------------------------------------------------------
# list_images
# ---------------------------------------------------------------------------

class TestListImages:
    def test_calls_downloaded_images(self, mock_cm):
        cm, api = mock_cm
        api.downloaded_images.return_value = ok(
            [{"repo_tag": "linuxserver/plex:latest"}]
        )
        result = cm.list_images()
        assert "linuxserver/plex" in result["data"][0]["repo_tag"]
        api.downloaded_images.assert_called_once()


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------

class TestListProjects:
    def test_returns_projects(self, mock_cm):
        cm, api = mock_cm
        api.list_projects.return_value = ok(
            [{"id": "uuid-1", "name": "media-stack"}]
        )
        result = cm.list_projects()
        assert result["data"][0]["id"] == "uuid-1"
        api.list_projects.assert_called_once()


# ---------------------------------------------------------------------------
# get_logs
# ---------------------------------------------------------------------------

class TestGetLogs:
    def test_passes_container_name(self, mock_cm):
        cm, api = mock_cm
        api.get_logs.return_value = ok({"logs": "starting up..."})
        cm.get_logs("plex")
        api.get_logs.assert_called_once_with(container_name="plex")


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------

class TestStartStop:
    def test_start_passes_name(self, mock_cm):
        cm, api = mock_cm
        api.start_container.return_value = ok({})
        cm.start("plex")
        api.start_container.assert_called_once_with("plex")

    def test_stop_passes_name(self, mock_cm):
        cm, api = mock_cm
        api.stop_container.return_value = ok({})
        cm.stop("plex")
        api.stop_container.assert_called_once_with("plex")

    def test_stop_raises_on_error(self, mock_cm):
        from tools.synology_client import SynologyAPIError
        cm, api = mock_cm
        api.stop_container.return_value = err(900)
        with pytest.raises(SynologyAPIError):
            cm.stop("plex")


# ---------------------------------------------------------------------------
# restart = stop + sleep(2) + start
# ---------------------------------------------------------------------------

class TestRestart:
    def test_restart_calls_stop_then_start(self, mock_cm, mocker):
        cm, api = mock_cm
        mocker.patch("time.sleep")
        api.stop_container.return_value = ok({})
        api.start_container.return_value = ok({})

        cm.restart("plex")

        api.stop_container.assert_called_once_with("plex")
        api.start_container.assert_called_once_with("plex")

    def test_restart_sleeps_2s_between_stop_and_start(self, mock_cm, mocker):
        cm, api = mock_cm
        call_order = []

        api.stop_container.side_effect = lambda name: (
            call_order.append("stop"), ok({})
        )[1]
        api.start_container.side_effect = lambda name: (
            call_order.append("start"), ok({})
        )[1]

        mocker.patch(
            "time.sleep",
            side_effect=lambda s: call_order.append(f"sleep({s})"),
        )

        cm.restart("plex")

        assert call_order == ["stop", "sleep(2)", "start"], (
            f"Expected stop → sleep(2) → start, got {call_order}"
        )

    def test_restart_raises_if_stop_fails(self, mock_cm, mocker):
        from tools.synology_client import SynologyAPIError
        cm, api = mock_cm
        mocker.patch("time.sleep")
        api.stop_container.return_value = err(900)

        with pytest.raises(SynologyAPIError):
            cm.restart("plex")

        # start should never have been called
        api.start_container.assert_not_called()
