"""
Shared fixtures for synology_client tests.

Unit tests mock the synology_api library classes so no real NAS is needed.
Integration tests are skipped unless SYNOLOGY_HOST is set in the environment.

Run unit tests:        pytest tests/
Run integration tests: SYNOLOGY_HOST=... pytest tests/ -m integration
"""

import pytest


# ---------------------------------------------------------------------------
# Environment fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def nas_env(monkeypatch):
    """Inject required NAS env vars for every test. Never touches real credentials."""
    monkeypatch.setenv("SYNOLOGY_HOST", "192.168.1.100")
    monkeypatch.setenv("SYNOLOGY_PORT", "5001")
    monkeypatch.setenv("SYNOLOGY_USER", "testuser")
    monkeypatch.setenv("SYNOLOGY_PASSWORD", "testpass")
    # Ensure SSH env vars are absent by default
    monkeypatch.delenv("SYNOLOGY_SSH_KEY_PATH", raising=False)
    monkeypatch.delenv("SYNOLOGY_SSH_PORT", raising=False)
    monkeypatch.delenv("SYNOLOGY_DOCKER_BIN", raising=False)


@pytest.fixture()
def cli_env(monkeypatch):
    """Simulate Claude Code CLI environment (CLAUDECODE=1)."""
    monkeypatch.setenv("CLAUDECODE", "1")


@pytest.fixture()
def web_env(monkeypatch):
    """Simulate web UI environment (CLAUDECODE unset)."""
    monkeypatch.delenv("CLAUDECODE", raising=False)


# ---------------------------------------------------------------------------
# Common API response builders
# ---------------------------------------------------------------------------

def ok(data: dict) -> dict:
    """Build a successful DSM API response."""
    return {"success": True, "data": data}


def err(code: int) -> dict:
    """Build a failed DSM API response with an error code."""
    return {"success": False, "error": {"code": code}}


# ---------------------------------------------------------------------------
# Integration marker
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires a real Synology NAS (SYNOLOGY_HOST must be set)",
    )


def pytest_collection_modifyitems(items):
    import os
    if not os.environ.get("SYNOLOGY_HOST") or os.environ.get("SYNOLOGY_HOST") == "192.168.1.100":
        skip = pytest.mark.skip(reason="SYNOLOGY_HOST not set to a real NAS")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)
