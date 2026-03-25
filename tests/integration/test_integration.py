"""
Integration tests — require a real Synology NAS.

These tests are skipped unless SYNOLOGY_HOST is set to a real NAS IP/hostname
(not the mock value 192.168.1.100 used in unit tests).

Run with:
    SYNOLOGY_HOST=10.0.0.5 SYNOLOGY_PORT=5001 \
    SYNOLOGY_USER=myuser SYNOLOGY_PASSWORD=mypass \
    pytest tests/integration/ -m integration -v

All tests are READ-ONLY (🟢 SAFE operations only). No files are created,
modified, or deleted on the NAS during integration testing.
"""

import pytest


# ---------------------------------------------------------------------------
# FileStation integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFileStationIntegration:
    def test_list_shares_returns_at_least_one_share(self):
        from tools.synology_client import get_filestation
        fs = get_filestation()
        result = fs.list_shares()
        assert result["success"] is True
        shares = result["data"]["shares"]
        assert len(shares) > 0, "Expected at least one shared folder on the NAS"

    def test_list_dir_on_first_share(self):
        from tools.synology_client import get_filestation
        fs = get_filestation()
        shares = fs.list_shares()["data"]["shares"]
        first_share_path = shares[0]["path"]
        result = fs.list_dir(first_share_path, limit=10)
        assert result["success"] is True
        assert "files" in result["data"]

    def test_list_share_links(self):
        from tools.synology_client import get_filestation
        fs = get_filestation()
        result = fs.list_share_links()
        assert result["success"] is True


# ---------------------------------------------------------------------------
# DownloadStation integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDownloadStationIntegration:
    def test_list_tasks_returns_valid_response(self):
        from tools.synology_client import get_downloadstation
        ds = get_downloadstation()
        result = ds.list_tasks()
        assert result["success"] is True
        assert "tasks" in result["data"]

    def test_get_config_returns_default_destination(self):
        from tools.synology_client import get_downloadstation
        ds = get_downloadstation()
        result = ds.get_config()
        assert result["success"] is True
        assert "default_destination" in result["data"]

    def test_get_statistics(self):
        from tools.synology_client import get_downloadstation
        ds = get_downloadstation()
        result = ds.get_statistics()
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Task Scheduler integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTaskSchedulerIntegration:
    def test_list_tasks_returns_valid_response(self):
        from tools.synology_client import get_taskscheduler
        ts = get_taskscheduler()
        result = ts.list_tasks()
        assert result["success"] is True
        assert "tasks" in result["data"]


# ---------------------------------------------------------------------------
# Container Manager integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestContainerManagerIntegration:
    def test_list_containers(self):
        from tools.synology_client import get_container_manager
        cm = get_container_manager()
        result = cm.list_containers()
        assert result["success"] is True

    def test_list_images(self):
        from tools.synology_client import get_container_manager
        cm = get_container_manager()
        result = cm.list_images()
        assert result["success"] is True

    def test_list_projects(self):
        from tools.synology_client import get_container_manager
        cm = get_container_manager()
        result = cm.list_projects()
        assert result["success"] is True
