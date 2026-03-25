"""
Tests for SynologySSH.

Key cases:
- SynologySSHNotAvailable raised when SSH_AVAILABLE is False
- get_ssh() raises SynologySSHNotAvailable when no paramiko
- connect(): uses key auth when SYNOLOGY_SSH_KEY_PATH is set, else password auth
- disconnect(): closes client
- context manager: connect on __enter__, disconnect on __exit__
- run(): returns (stdout, stderr, exit_code); raises SynologySSHError on transport failure
- run(): raises SynologySSHError when not connected
- docker_exec / docker_pull / docker_build / docker_logs / docker_inspect: correct commands
- docker commands use SYNOLOGY_DOCKER_BIN override
"""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ssh_client(stdout_data=b"output\n", stderr_data=b"", exit_code=0):
    """Build a mock paramiko.SSHClient with exec_command wired up."""
    stdout_channel = MagicMock()
    stdout_channel.recv_exit_status.return_value = exit_code

    stdout_obj = MagicMock()
    stdout_obj.channel = stdout_channel
    stdout_obj.read.return_value = stdout_data

    stderr_obj = MagicMock()
    stderr_obj.read.return_value = stderr_data

    client = MagicMock()
    client.exec_command.return_value = (MagicMock(), stdout_obj, stderr_obj)
    return client


# ---------------------------------------------------------------------------
# SynologySSHNotAvailable when paramiko is absent
# ---------------------------------------------------------------------------

class TestSSHNotAvailable:
    def test_raises_when_ssh_not_available(self, monkeypatch):
        """get_ssh() must raise SynologySSHNotAvailable when SSH_AVAILABLE is False."""
        import tools.synology_client as client_module
        monkeypatch.setattr(client_module, "SSH_AVAILABLE", False)

        from tools.synology_client import SynologySSHNotAvailable, get_ssh
        with pytest.raises(SynologySSHNotAvailable):
            get_ssh()

    def test_not_available_message_mentions_paramiko(self):
        from tools.synology_client import SynologySSHNotAvailable
        exc = SynologySSHNotAvailable()
        msg = str(exc).lower()
        assert "paramiko" in msg
        assert "pip install" in str(exc)

    def test_not_available_is_ssh_error(self):
        from tools.synology_client import SynologySSHNotAvailable, SynologySSHError
        exc = SynologySSHNotAvailable()
        assert isinstance(exc, SynologySSHError)


# ---------------------------------------------------------------------------
# connect() — key vs password auth
# ---------------------------------------------------------------------------

class TestConnect:
    def _make_ssh(self, monkeypatch, key_path=None):
        """Helper: build SynologySSH with paramiko mocked out."""
        import tools.synology_client as client_module
        monkeypatch.setattr(client_module, "SSH_AVAILABLE", True)

        mock_paramiko = MagicMock()
        mock_paramiko.SSHClient.return_value = MagicMock()
        mock_paramiko.AutoAddPolicy = MagicMock()

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            # Re-patch the module-level paramiko reference
            monkeypatch.setattr(client_module, "paramiko", mock_paramiko, raising=False)

            from tools.synology_client import SynologySSH
            if key_path:
                monkeypatch.setenv("SYNOLOGY_SSH_KEY_PATH", key_path)
            else:
                monkeypatch.delenv("SYNOLOGY_SSH_KEY_PATH", raising=False)

            ssh = SynologySSH()
            return ssh, mock_paramiko

    def test_uses_key_when_key_path_set(self, monkeypatch):
        ssh, mock_paramiko = self._make_ssh(monkeypatch, key_path="/home/user/.ssh/id_rsa")
        client_instance = mock_paramiko.SSHClient.return_value
        ssh.connect()
        call_kwargs = client_instance.connect.call_args.kwargs
        assert call_kwargs.get("key_filename") == "/home/user/.ssh/id_rsa"
        assert "password" not in call_kwargs

    def test_uses_password_when_no_key(self, monkeypatch):
        ssh, mock_paramiko = self._make_ssh(monkeypatch)
        client_instance = mock_paramiko.SSHClient.return_value
        ssh.connect()
        call_kwargs = client_instance.connect.call_args.kwargs
        assert call_kwargs.get("password") == "testpass"  # from nas_env fixture
        assert "key_filename" not in call_kwargs

    def test_uses_ssh_port_not_dsm_port(self, monkeypatch):
        monkeypatch.setenv("SYNOLOGY_SSH_PORT", "2222")
        ssh, mock_paramiko = self._make_ssh(monkeypatch)
        client_instance = mock_paramiko.SSHClient.return_value
        ssh.connect()
        call_kwargs = client_instance.connect.call_args.kwargs
        assert call_kwargs["port"] == 2222


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

class TestRun:
    def _connected_ssh(self, monkeypatch, mock_client=None):
        import tools.synology_client as client_module
        monkeypatch.setattr(client_module, "SSH_AVAILABLE", True)

        from tools.synology_client import SynologySSH
        ssh = SynologySSH.__new__(SynologySSH)
        ssh._host = "192.168.1.100"
        ssh._port = 22
        ssh._user = "testuser"
        ssh._password = "testpass"
        ssh._key_path = None
        ssh._docker_bin = "/var/packages/ContainerManager/target/usr/bin/docker"
        ssh._timeout = 30
        ssh._client = mock_client or _make_ssh_client()
        return ssh

    def test_returns_stdout_stderr_exit_code(self, monkeypatch):
        client = _make_ssh_client(stdout_data=b"hello\n", stderr_data=b"warn\n", exit_code=0)
        ssh = self._connected_ssh(monkeypatch, client)
        stdout, stderr, code = ssh.run("echo hello")
        assert stdout == "hello\n"
        assert stderr == "warn\n"
        assert code == 0

    def test_non_zero_exit_does_not_raise(self, monkeypatch):
        client = _make_ssh_client(exit_code=1)
        ssh = self._connected_ssh(monkeypatch, client)
        _, _, code = ssh.run("false")
        assert code == 1

    def test_raises_when_not_connected(self, monkeypatch):
        from tools.synology_client import SynologySSHError
        import tools.synology_client as client_module
        monkeypatch.setattr(client_module, "SSH_AVAILABLE", True)

        from tools.synology_client import SynologySSH
        ssh = SynologySSH.__new__(SynologySSH)
        ssh._client = None
        ssh._timeout = 30

        with pytest.raises(SynologySSHError, match="Not connected"):
            ssh.run("hostname")

    def test_raises_ssh_error_on_transport_failure(self, monkeypatch):
        from tools.synology_client import SynologySSHError
        client = MagicMock()
        client.exec_command.side_effect = Exception("Transport closed")
        ssh = self._connected_ssh(monkeypatch, client)
        with pytest.raises(SynologySSHError):
            ssh.run("hostname")


# ---------------------------------------------------------------------------
# docker helpers
# ---------------------------------------------------------------------------

class TestDockerHelpers:
    def _connected_ssh(self, monkeypatch, docker_bin=None):
        import tools.synology_client as client_module
        monkeypatch.setattr(client_module, "SSH_AVAILABLE", True)

        default_bin = "/var/packages/ContainerManager/target/usr/bin/docker"
        from tools.synology_client import SynologySSH
        ssh = SynologySSH.__new__(SynologySSH)
        ssh._host = "192.168.1.100"
        ssh._port = 22
        ssh._user = "testuser"
        ssh._password = "testpass"
        ssh._key_path = None
        ssh._docker_bin = docker_bin or default_bin
        ssh._timeout = 30
        ssh._client = _make_ssh_client()
        return ssh

    def test_docker_exec_builds_correct_command(self, monkeypatch):
        ssh = self._connected_ssh(monkeypatch)
        ssh.docker_exec("plex", "ls /data")
        cmd = ssh._client.exec_command.call_args.args[0]
        assert "/var/packages/ContainerManager/target/usr/bin/docker" in cmd
        assert "exec plex ls /data" in cmd

    def test_docker_pull_builds_correct_command(self, monkeypatch):
        ssh = self._connected_ssh(monkeypatch)
        ssh.docker_pull("linuxserver/plex:latest")
        cmd = ssh._client.exec_command.call_args.args[0]
        assert "pull linuxserver/plex:latest" in cmd

    def test_docker_build_includes_tag_and_context(self, monkeypatch):
        ssh = self._connected_ssh(monkeypatch)
        ssh.docker_build("/volume1/myapp", "myapp:v2")
        cmd = ssh._client.exec_command.call_args.args[0]
        assert "build -t myapp:v2" in cmd
        assert "/volume1/myapp" in cmd

    def test_docker_build_with_dockerfile(self, monkeypatch):
        ssh = self._connected_ssh(monkeypatch)
        ssh.docker_build("/volume1/myapp", "myapp:v2", dockerfile="Dockerfile.prod")
        cmd = ssh._client.exec_command.call_args.args[0]
        assert "-f Dockerfile.prod" in cmd

    def test_docker_logs_default_tail(self, monkeypatch):
        ssh = self._connected_ssh(monkeypatch)
        ssh.docker_logs("plex")
        cmd = ssh._client.exec_command.call_args.args[0]
        assert "logs --tail 100 plex" in cmd

    def test_docker_logs_custom_tail(self, monkeypatch):
        ssh = self._connected_ssh(monkeypatch)
        ssh.docker_logs("plex", tail=500)
        cmd = ssh._client.exec_command.call_args.args[0]
        assert "logs --tail 500 plex" in cmd

    def test_docker_inspect_passes_container(self, monkeypatch):
        ssh = self._connected_ssh(monkeypatch)
        ssh.docker_inspect("plex")
        cmd = ssh._client.exec_command.call_args.args[0]
        assert "inspect plex" in cmd

    def test_custom_docker_bin_used(self, monkeypatch):
        ssh = self._connected_ssh(monkeypatch, docker_bin="/usr/bin/docker")
        ssh.docker_logs("plex")
        cmd = ssh._client.exec_command.call_args.args[0]
        assert cmd.startswith("/usr/bin/docker")


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_connect_on_enter_disconnect_on_exit(self, monkeypatch):
        import tools.synology_client as client_module
        monkeypatch.setattr(client_module, "SSH_AVAILABLE", True)

        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AutoAddPolicy = MagicMock()

        monkeypatch.setattr(client_module, "paramiko", mock_paramiko, raising=False)
        monkeypatch.delenv("SYNOLOGY_SSH_KEY_PATH", raising=False)

        from tools.synology_client import SynologySSH
        ssh = SynologySSH()

        with ssh:
            mock_client.connect.assert_called_once()

        mock_client.close.assert_called_once()
