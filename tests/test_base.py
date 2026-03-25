"""
Tests for module-level helpers: _check_response, _get_env, exceptions,
SSH_AVAILABLE, and RUNNING_IN_CLI.
"""

import importlib
import os
import pytest

from tools.synology_client import (
    _check_response,
    _get_env,
    SynologyAPIError,
    SynologyAuthError,
    SynologySSHError,
    SynologySSHNotAvailable,
)
from tests.conftest import ok, err


# ---------------------------------------------------------------------------
# _get_env
# ---------------------------------------------------------------------------

class TestGetEnv:
    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("SYNOLOGY_HOST", "10.0.0.1")
        assert _get_env("SYNOLOGY_HOST") == "10.0.0.1"

    def test_returns_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("SYNOLOGY_PORT", raising=False)
        assert _get_env("SYNOLOGY_PORT", "5001") == "5001"

    def test_raises_auth_error_when_missing_no_default(self, monkeypatch):
        monkeypatch.delenv("SYNOLOGY_HOST", raising=False)
        with pytest.raises(SynologyAuthError) as exc:
            _get_env("SYNOLOGY_HOST")
        assert "SYNOLOGY_HOST" in str(exc.value)

    def test_error_message_names_the_variable(self, monkeypatch):
        monkeypatch.delenv("SYNOLOGY_PASSWORD", raising=False)
        with pytest.raises(SynologyAuthError, match="SYNOLOGY_PASSWORD"):
            _get_env("SYNOLOGY_PASSWORD")


# ---------------------------------------------------------------------------
# _check_response
# ---------------------------------------------------------------------------

class TestCheckResponse:
    def test_returns_result_on_success(self):
        result = ok({"files": []})
        assert _check_response(result, "ctx") is result

    def test_raises_api_error_on_failure(self):
        with pytest.raises(SynologyAPIError):
            _check_response(err(119), "FileStation.list_shares")

    def test_error_code_is_preserved(self):
        with pytest.raises(SynologyAPIError) as exc:
            _check_response(err(900), "FileStation.list_dir")
        assert exc.value.error_code == 900

    def test_context_is_preserved(self):
        with pytest.raises(SynologyAPIError) as exc:
            _check_response(err(105), "FileStation.delete")
        assert exc.value.context == "FileStation.delete"

    def test_missing_success_key_raises(self):
        """A response with no 'success' key is treated as failure."""
        with pytest.raises(SynologyAPIError):
            _check_response({"data": {}}, "ctx")

    def test_success_false_without_error_key(self):
        """success=False with no error dict uses code -1."""
        with pytest.raises(SynologyAPIError) as exc:
            _check_response({"success": False}, "ctx")
        assert exc.value.error_code == -1


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class TestExceptionHierarchy:
    def test_api_error_is_client_error(self):
        from tools.synology_client import SynologyClientError
        exc = SynologyAPIError(119, "test")
        assert isinstance(exc, SynologyClientError)

    def test_auth_error_is_client_error(self):
        from tools.synology_client import SynologyClientError
        exc = SynologyAuthError("missing var")
        assert isinstance(exc, SynologyClientError)

    def test_ssh_not_available_is_ssh_error(self):
        exc = SynologySSHNotAvailable()
        assert isinstance(exc, SynologySSHError)

    def test_ssh_not_available_message(self):
        exc = SynologySSHNotAvailable()
        assert "paramiko" in str(exc).lower()
        assert "pip install" in str(exc)


# ---------------------------------------------------------------------------
# SSH_AVAILABLE flag
# ---------------------------------------------------------------------------

class TestSSHAvailable:
    def test_ssh_available_reflects_paramiko(self):
        """SSH_AVAILABLE should be True if paramiko is importable."""
        try:
            import paramiko  # noqa: F401
            paramiko_present = True
        except ImportError:
            paramiko_present = False

        import tools.synology_client as client
        assert client.SSH_AVAILABLE == paramiko_present


# ---------------------------------------------------------------------------
# RUNNING_IN_CLI flag
# ---------------------------------------------------------------------------

class TestRunningInCLI:
    def test_true_when_claudecode_is_1(self, monkeypatch):
        monkeypatch.setenv("CLAUDECODE", "1")
        # Re-import to pick up new env state
        import tools.synology_client as client
        importlib.reload(client)
        assert client.RUNNING_IN_CLI is True

    def test_false_when_claudecode_unset(self, monkeypatch):
        monkeypatch.delenv("CLAUDECODE", raising=False)
        import tools.synology_client as client
        importlib.reload(client)
        assert client.RUNNING_IN_CLI is False

    def test_false_when_claudecode_is_other_value(self, monkeypatch):
        monkeypatch.setenv("CLAUDECODE", "true")  # not "1"
        import tools.synology_client as client
        importlib.reload(client)
        assert client.RUNNING_IN_CLI is False
