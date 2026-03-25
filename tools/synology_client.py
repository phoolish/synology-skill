"""
Synology NAS client library wrapping synology-api.

Usage:
    from tools.synology_client import get_filestation, get_downloadstation
    from tools.synology_client import get_taskscheduler, get_container_manager
    from tools.synology_client import get_ssh, SSH_AVAILABLE

Credentials are read exclusively from environment variables:
    SYNOLOGY_HOST       NAS hostname or IP (required)
    SYNOLOGY_PORT       DSM HTTPS port, default 5001 (required)
    SYNOLOGY_USER       DSM username (required)
    SYNOLOGY_PASSWORD   DSM password (required)
    SYNOLOGY_SSH_KEY_PATH   Path to SSH private key (optional, preferred over password)
    SYNOLOGY_SSH_PORT   SSH port, default 22 (optional — different from SYNOLOGY_PORT)
    SYNOLOGY_DOCKER_BIN Docker binary path on NAS (optional)

Requires: pip install synology-api
Optional:  pip install paramiko  (needed for SynologySSH)
"""

from __future__ import annotations

import os
import time
from typing import Any

# Hard dependency — fail loudly if missing
from synology_api.filestation import FileStation
from synology_api.downloadstation import DownloadStation
from synology_api.task_scheduler import TaskScheduler
from synology_api.docker_api import Docker

# Optional SSH support
try:
    import paramiko
    SSH_AVAILABLE = True
except ImportError:
    SSH_AVAILABLE = False

# Default Docker binary path on DSM — not always in $PATH for SSH users
_DOCKER_BIN_DEFAULT = "/var/packages/ContainerManager/target/usr/bin/docker"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SynologyClientError(Exception):
    """Base exception for all synology_client errors."""


class SynologyAPIError(SynologyClientError):
    """DSM API returned success=false."""

    def __init__(self, error_code: int, context: str) -> None:
        self.error_code = error_code
        self.context = context
        super().__init__(
            f"Synology API error {error_code} in {context}. "
            f"See references/dsm-api-gaps.md for error code meanings."
        )


class SynologyAuthError(SynologyClientError):
    """Missing environment variable or login failure."""


class SynologySSHError(SynologyClientError):
    """SSH transport failure."""


class SynologySSHNotAvailable(SynologySSHError):
    """paramiko is not installed."""

    def __init__(self) -> None:
        super().__init__(
            "paramiko is not installed. Install with: pip install paramiko"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_env(key: str, default: str | None = None) -> str:
    """Read an environment variable; raise SynologyAuthError if missing and no default."""
    value = os.environ.get(key, default)
    if value is None:
        raise SynologyAuthError(
            f"Required environment variable {key!r} is not set. "
            f"See README.md for credential setup instructions."
        )
    return value


def _check_response(result: dict, context: str) -> dict:
    """
    Validate a synology-api response dict.

    Raises SynologyAPIError if result['success'] is False.
    Returns result unchanged on success so callers can chain: data = _check_response(...)['data']
    """
    if not result.get("success", False):
        error_info = result.get("error", {})
        code = error_info.get("code", -1) if isinstance(error_info, dict) else -1
        raise SynologyAPIError(code, context)
    return result


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class SynologyBase:
    """
    Abstract base for DSM API wrappers.

    Subclasses must assign _lib_class before calling super().__init__().
    All credentials are read from environment variables.

    Session-sharing caveat: synology-api uses a class-level shared session.
    Instantiating the same library class twice reuses auth. Calling logout()
    on any instance invalidates all. On session expiry (error 119), re-instantiate.
    """

    _lib_class: type  # assigned by subclasses

    def __init__(self) -> None:
        host = _get_env("SYNOLOGY_HOST")
        port = _get_env("SYNOLOGY_PORT", "5001")
        user = _get_env("SYNOLOGY_USER")
        password = _get_env("SYNOLOGY_PASSWORD")
        self._api: Any = self._lib_class(
            host,
            port,
            user,
            password,
            secure=True,
            cert_verify=False,
            dsm_version=7,
            debug=False,
            otp_code=None,
        )

    def logout(self) -> None:
        """Log out. WARNING: invalidates all shared sessions for this library class."""
        self._api.logout()


# ---------------------------------------------------------------------------
# FileStation
# ---------------------------------------------------------------------------

class SynologyFileStation(SynologyBase):
    """
    FileStation operations.

    Authorization tiers (see SKILL.md):
      🟢 SAFE:       list_shares, list_dir, file_info, search, list_share_links,
                     upload, create_dir, rename, copy, create_share_link
      🔵 SENSITIVE:  download  (file contents may be private)
      ⚠️ DESTRUCTIVE: move, delete, delete_share_link
    """

    _lib_class = FileStation

    def list_shares(self) -> dict:
        """List all shared folders. 🟢 SAFE"""
        return _check_response(self._api.get_list_share(), "FileStation.list_shares")

    def list_dir(self, path: str, offset: int = 0, limit: int = 100) -> dict:
        """List directory contents. 🟢 SAFE. Paths: /volume1/share/folder"""
        return _check_response(
            self._api.get_file_list(folder_path=path, offset=offset, limit=limit),
            "FileStation.list_dir",
        )

    def file_info(self, paths: list[str]) -> dict:
        """Get metadata for one or more files/folders. 🟢 SAFE"""
        return _check_response(
            self._api.get_file_info(path=",".join(paths)),
            "FileStation.file_info",
        )

    def search(self, path: str, pattern: str, timeout_seconds: int = 30) -> dict:
        """
        Search for files matching pattern under path. 🟢 SAFE

        Hides the async DSM search API: polls until finished or timeout_seconds elapses.
        Raises SynologyAPIError with context 'search_timeout' if search doesn't finish.
        """
        start = _check_response(
            self._api.search_start(folder_path=path, pattern=pattern),
            "FileStation.search_start",
        )
        task_id = start["data"]["taskid"]

        deadline = time.time() + timeout_seconds
        while True:
            result = _check_response(
                self._api.get_search_list(task_id=task_id),
                "FileStation.search_poll",
            )
            if result["data"].get("finished", False):
                return result
            if time.time() > deadline:
                raise SynologyAPIError(-1, "search_timeout")
            time.sleep(0.5)

    def upload(self, local_path: str, remote_dir: str, overwrite: bool = False) -> dict:
        """Upload a file to the NAS. 🟢 SAFE"""
        return _check_response(
            self._api.upload_file(
                dest_folder_path=remote_dir,
                file_path=local_path,
                overwrite=overwrite,
            ),
            "FileStation.upload",
        )

    def download(self, remote_path: str, dest_dir: str) -> bytes:
        """
        Download a file from the NAS. 🔵 SENSITIVE — file contents may be private.

        Before calling: state intent — "I'm going to download [remote_path],
        which may contain private data."
        Returns raw bytes. Caller is responsible for writing to dest_dir.
        """
        return self._api.get_file(path=remote_path, mode="download")

    def create_dir(self, path: str) -> dict:
        """Create a directory. 🟢 SAFE. path is the full path including new dir name."""
        folder = os.path.basename(path)
        parent = os.path.dirname(path)
        return _check_response(
            self._api.create_folder(folder_path=parent, name=folder),
            "FileStation.create_dir",
        )

    def rename(self, path: str, new_name: str) -> dict:
        """Rename a file or folder (name only, not path). 🟢 SAFE"""
        return _check_response(
            self._api.rename_entry(path=path, name=new_name),
            "FileStation.rename",
        )

    def copy(self, source: str, dest_dir: str) -> dict:
        """
        Copy a file or folder. 🟢 SAFE. Polls until operation completes.
        Returns the final status dict.
        """
        return self._run_copy_move(source, dest_dir, remove_src=False)

    def move(self, source: str, dest_dir: str) -> dict:
        """
        Move a file or folder. ⚠️ DESTRUCTIVE — removes the source.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will move [source] to [dest_dir], removing it from its current location."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.
        """
        return self._run_copy_move(source, dest_dir, remove_src=True)

    def _run_copy_move(self, source: str, dest_dir: str, remove_src: bool) -> dict:
        start = _check_response(
            self._api.start_copy_move(
                path=source,
                dest_folder_path=dest_dir,
                overwrite=False,
                remove_src=remove_src,
            ),
            "FileStation.copy_move_start",
        )
        task_id = start["data"]["taskid"]
        while True:
            status = _check_response(
                self._api.get_copy_move_status(task_id=task_id),
                "FileStation.copy_move_status",
            )
            if status["data"].get("finished", False):
                return status
            time.sleep(0.5)

    def delete(self, path: str) -> dict:
        """
        Delete a file or folder permanently. ⚠️ DESTRUCTIVE — IRREVERSIBLE.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will permanently delete [path] from the NAS."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.

        Uses delete_blocking_function() — synchronous, returns when complete.
        """
        return _check_response(
            self._api.delete_blocking_function(path=path),
            "FileStation.delete",
        )

    def create_share_link(
        self,
        path: str,
        expires_days: int | None = None,
        password: str | None = None,
    ) -> dict:
        """Create a public share link for a file. 🟢 SAFE"""
        kwargs: dict[str, Any] = {"path": path}
        if expires_days is not None:
            kwargs["date_expired"] = expires_days
        if password is not None:
            kwargs["link_password"] = password
        return _check_response(
            self._api.sharing_create_link(**kwargs),
            "FileStation.create_share_link",
        )

    def list_share_links(self) -> dict:
        """List all active share links. 🟢 SAFE"""
        return _check_response(
            self._api.sharing_get_info(),
            "FileStation.list_share_links",
        )

    def delete_share_link(self, link_id: str) -> dict:
        """
        Delete a share link. ⚠️ DESTRUCTIVE — link becomes immediately inaccessible.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will permanently delete share link [link_id]."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.
        """
        return _check_response(
            self._api.sharing_delete_link(link_id=link_id),
            "FileStation.delete_share_link",
        )


# ---------------------------------------------------------------------------
# DownloadStation
# ---------------------------------------------------------------------------

class SynologyDownloadStation(SynologyBase):
    """
    DownloadStation operations.

    Authorization tiers (see SKILL.md):
      🟢 SAFE:        list_tasks, task_info, get_config, get_statistics,
                      add_url, pause, resume
      ⚠️ DESTRUCTIVE: delete
    """

    _lib_class = DownloadStation

    def list_tasks(self, offset: int = 0, limit: int = 100) -> dict:
        """
        List download tasks. 🟢 SAFE

        Task status values: waiting, downloading, paused, finishing, finished,
        hash_checking, seeding, filehosting_waiting, extracting, error
        """
        return _check_response(
            self._api.tasks_list(
                offset=offset,
                limit=limit,
                additional_param="transfer,detail,file",
            ),
            "DownloadStation.list_tasks",
        )

    def task_info(self, task_id: str) -> dict:
        """Get detailed info for a specific task. 🟢 SAFE"""
        return _check_response(
            self._api.tasks_info(task_id=task_id),
            "DownloadStation.task_info",
        )

    def add_url(self, url: str, destination: str = "") -> dict:
        """
        Add a download task by URL. 🟢 SAFE

        Accepts: HTTP/HTTPS URLs, magnet: URIs, .torrent file URLs.
        destination: remote path for downloaded files; "" uses the default folder
        from get_config()['data']['default_destination'].
        """
        return _check_response(
            self._api.create_task(url=url, destination=destination),
            "DownloadStation.add_url",
        )

    def pause(self, task_id: str) -> dict:
        """Pause a downloading task. 🟢 SAFE"""
        return _check_response(
            self._api.tasks_action(action="pause", task_id=task_id),
            "DownloadStation.pause",
        )

    def resume(self, task_id: str) -> dict:
        """Resume a paused task. 🟢 SAFE"""
        return _check_response(
            self._api.tasks_action(action="resume", task_id=task_id),
            "DownloadStation.resume",
        )

    def delete(self, task_id: str, force: bool = False) -> dict:
        """
        Delete a download task. ⚠️ DESTRUCTIVE — removes the task and its metadata.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will delete download task [task_id]."
           If force=True add: "The task will be deleted even if currently downloading."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.

        force=True: delete even if task is actively downloading.
        """
        return _check_response(
            self._api.tasks_action(
                action="delete",
                task_id=task_id,
                force_complete=force,
            ),
            "DownloadStation.delete",
        )

    def get_config(self) -> dict:
        """Get DownloadStation configuration (default destination, speed limits). 🟢 SAFE"""
        return _check_response(
            self._api.get_config(),
            "DownloadStation.get_config",
        )

    def get_statistics(self) -> dict:
        """Get overall transfer statistics. 🟢 SAFE"""
        return _check_response(
            self._api.get_statistic_info(),
            "DownloadStation.get_statistics",
        )


# ---------------------------------------------------------------------------
# Task Scheduler
# ---------------------------------------------------------------------------

class SynologyTaskScheduler(SynologyBase):
    """
    Task Scheduler operations.

    Authorization tiers (see SKILL.md):
      🟢 SAFE:        list_tasks, get_task_results, enable, disable
      🔵 SENSITIVE:   get_task (returns script source code),
                      create_script_task (creates executable code on NAS)
      ⚠️ DESTRUCTIVE: run_now, delete, modify_script_task
    """

    _lib_class = TaskScheduler

    def list_tasks(
        self, sort_by: str = "name", sort_direction: str = "ASC"
    ) -> dict:
        """
        List all scheduled tasks. 🟢 SAFE

        task_id is at result['data']['tasks'][n]['id'].
        owner is at result['data']['tasks'][n]['owner'].
        """
        return _check_response(
            self._api.get_task_list(
                sort_by=sort_by, sort_direction=sort_direction
            ),
            "TaskScheduler.list_tasks",
        )

    def get_task(
        self, task_id: int, owner: str, task_type: str = "script"
    ) -> dict:
        """
        Get task configuration including script source. 🔵 SENSITIVE

        Before calling — intent declaration (see SKILL.md):
        "I'm going to read task [task_id], which may contain script source code
        with credentials or sensitive commands."

        owner: DSM username who owns the task (from list_tasks result).
        task_type: "script" | "beep_control" | "service_control"
        """
        return _check_response(
            self._api.get_task_config(
                task_id=task_id,
                real_owner=owner,
                type=task_type,
            ),
            "TaskScheduler.get_task",
        )

    def get_task_results(self, task_id: int) -> dict:
        """
        Get execution history for a task. 🟢 SAFE

        Returns array of {task_id, time, duration, exit_code}.
        """
        return _check_response(
            self._api.get_task_results(task_id=task_id),
            "TaskScheduler.get_task_results",
        )

    def run_now(self, task_id: int, owner: str) -> dict:
        """
        Trigger a task to run immediately. ⚠️ DESTRUCTIVE — executes arbitrary script.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will immediately execute task [task_id] owned by [owner]."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.
        """
        return _check_response(
            self._api.task_run(task_id=task_id, real_owner=owner),
            "TaskScheduler.run_now",
        )

    def enable(self, task_id: int, owner: str) -> dict:
        """Enable a scheduled task. 🟢 SAFE"""
        return _check_response(
            self._api.task_set_enable(
                task_id=task_id, real_owner=owner, enable=True
            ),
            "TaskScheduler.enable",
        )

    def disable(self, task_id: int, owner: str) -> dict:
        """Disable a scheduled task. 🟢 SAFE"""
        return _check_response(
            self._api.task_set_enable(
                task_id=task_id, real_owner=owner, enable=False
            ),
            "TaskScheduler.disable",
        )

    def delete(self, task_id: int, owner: str) -> dict:
        """
        Delete a scheduled task permanently. ⚠️ DESTRUCTIVE — IRREVERSIBLE.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will permanently delete task [task_id] owned by [owner]."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.
        """
        return _check_response(
            self._api.task_delete(task_id=task_id, real_owner=owner),
            "TaskScheduler.delete",
        )

    def create_script_task(
        self,
        name: str,
        owner: str,
        script: str,
        schedule: dict,
        enable: bool = True,
        notify_email: str = "",
        notify_only_on_error: bool = False,
    ) -> dict:
        """
        Create a new scheduled script task. 🔵 SENSITIVE

        Before calling — intent declaration (see SKILL.md):
        "I'm going to create a scheduled script on the NAS named [name].
        It will run as [owner] on the schedule [schedule summary]."

        schedule dict keys (see references/taskscheduler-api.md for full schema):
            run_frequently: bool        True=repeat, False=one-time
            run_days: str               comma-separated 0-6 (0=Sunday)
            repeat: str                 "daily" | "weekly" | "monthly"
            start_time_h: int           0-23
            start_time_m: int           0-59
            same_day_repeat_h: int      0 = no intraday repeat
            same_day_repeat_m: int
            same_day_repeat_until: int | None
        """
        return _check_response(
            self._api.create_script_task(
                task_name=name,
                owner=owner,
                script=script,
                enable=enable,
                run_frequently=schedule["run_frequently"],
                run_days=schedule.get("run_days", "0,1,2,3,4,5,6"),
                repeat=schedule.get("repeat", "daily"),
                start_time_h=schedule.get("start_time_h", 0),
                start_time_m=schedule.get("start_time_m", 0),
                same_day_repeat_h=schedule.get("same_day_repeat_h", 0),
                same_day_repeat_m=schedule.get("same_day_repeat_m", 0),
                same_day_repeat_until=schedule.get("same_day_repeat_until"),
                notify_email=notify_email,
                notify_only_on_error=notify_only_on_error,
            ),
            "TaskScheduler.create_script_task",
        )

    def modify_script_task(self, task_id: int, **kwargs: Any) -> dict:
        """
        Modify an existing script task. ⚠️ DESTRUCTIVE — overwrites current configuration.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will modify task [task_id]. Changes: [list kwargs keys]."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.

        kwargs: any subset of create_script_task parameters to update.
        """
        return _check_response(
            self._api.modify_script_task(task_id=task_id, **kwargs),
            "TaskScheduler.modify_script_task",
        )


# ---------------------------------------------------------------------------
# Container Manager
# ---------------------------------------------------------------------------

class SynologyContainerManager(SynologyBase):
    """
    Container Manager (Docker) operations via DSM API.

    Authorization tiers (see SKILL.md):
      🟢 SAFE:        list_containers, container_stats, list_images,
                      list_projects, start
      🔵 SENSITIVE:   get_logs (may contain tokens/passwords in output)
      ⚠️ DESTRUCTIVE: stop, restart

    For exec, pull, build, full logs, or docker inspect: use SynologySSH.
    The DSM API does not expose these operations.
    """

    _lib_class = Docker

    def list_containers(self) -> dict:
        """List all containers (running and stopped). 🟢 SAFE"""
        return _check_response(
            self._api.containers(),
            "ContainerManager.list_containers",
        )

    def container_stats(self) -> dict:
        """Get live resource usage stats for all containers. 🟢 SAFE"""
        return _check_response(
            self._api.docker_stats(),
            "ContainerManager.container_stats",
        )

    def list_images(self) -> dict:
        """List all downloaded images. 🟢 SAFE"""
        return _check_response(
            self._api.downloaded_images(),
            "ContainerManager.list_images",
        )

    def list_projects(self) -> dict:
        """
        List all Docker Compose projects. 🟢 SAFE

        Project operations use IDs from result['data'][n]['id'], not names.
        """
        return _check_response(
            self._api.list_projects(),
            "ContainerManager.list_projects",
        )

    def get_logs(self, container_name: str) -> dict:
        """
        Get container logs via DSM API. 🔵 SENSITIVE

        Before calling — intent declaration (see SKILL.md):
        "I'm going to read logs for container [container_name],
        which may contain passwords, tokens, or other sensitive output."

        NOTE: API logs are often truncated. For full logs use SynologySSH.docker_logs().
        """
        return _check_response(
            self._api.get_logs(container_name=container_name),
            "ContainerManager.get_logs",
        )

    def start(self, container_name: str) -> dict:
        """Start a stopped container. 🟢 SAFE"""
        return _check_response(
            self._api.start_container(container_name),
            "ContainerManager.start",
        )

    def stop(self, container_name: str) -> dict:
        """
        Stop a running container. ⚠️ DESTRUCTIVE — interrupts the running service.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will stop container [container_name], interrupting its service."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.
        """
        return _check_response(
            self._api.stop_container(container_name),
            "ContainerManager.stop",
        )

    def restart(self, container_name: str) -> dict:
        """
        Restart a container (stop then start). ⚠️ DESTRUCTIVE — causes service interruption.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will restart container [container_name], causing a brief service interruption."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.

        NOTE: No native DSM API restart method; this calls stop() + 2s sleep + start().
        """
        self.stop(container_name)
        time.sleep(2)
        return self.start(container_name)


# ---------------------------------------------------------------------------
# SSH client
# ---------------------------------------------------------------------------

class SynologySSH:
    """
    SSH access to the Synology NAS host.

    Requires paramiko. Check SSH_AVAILABLE before instantiating.
    Raises SynologySSHNotAvailable if paramiko is not installed.

    Preferred usage — context manager:
        with get_ssh() as ssh:
            stdout, stderr, exit_code = ssh.run("hostname")

    Port note: SYNOLOGY_PORT is the DSM HTTPS port (default 5001).
    SSH uses SYNOLOGY_SSH_PORT (default 22). These are different services.

    Docker PATH note: The docker binary may not be in $PATH for SSH users.
    Default path: /var/packages/ContainerManager/target/usr/bin/docker
    Override via SYNOLOGY_DOCKER_BIN env var.
    If docker commands return exit_code=127, verify the binary path.
    """

    def __init__(self, timeout: int = 30) -> None:
        if not SSH_AVAILABLE:
            raise SynologySSHNotAvailable()
        self._host = _get_env("SYNOLOGY_HOST")
        self._port = int(_get_env("SYNOLOGY_SSH_PORT", "22"))
        self._user = _get_env("SYNOLOGY_USER")
        self._password = _get_env("SYNOLOGY_PASSWORD")
        self._key_path = os.environ.get("SYNOLOGY_SSH_KEY_PATH")
        self._docker_bin = os.environ.get("SYNOLOGY_DOCKER_BIN", _DOCKER_BIN_DEFAULT)
        self._timeout = timeout
        self._client: paramiko.SSHClient | None = None  # type: ignore[name-defined]

    def connect(self) -> None:
        """Open SSH connection. Key auth if SYNOLOGY_SSH_KEY_PATH is set, else password."""
        client = paramiko.SSHClient()  # type: ignore[attr-defined]
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # type: ignore[attr-defined]
        connect_kwargs: dict[str, Any] = {
            "hostname": self._host,
            "port": self._port,
            "username": self._user,
            "timeout": self._timeout,
        }
        if self._key_path:
            connect_kwargs["key_filename"] = self._key_path
        else:
            connect_kwargs["password"] = self._password
        try:
            client.connect(**connect_kwargs)
        except Exception as exc:
            raise SynologySSHError(f"SSH connection failed: {exc}") from exc
        self._client = client

    def disconnect(self) -> None:
        """Close SSH connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "SynologySSH":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()

    def run(
        self, command: str, timeout: int | None = None
    ) -> tuple[str, str, int]:
        """
        Run a shell command on the NAS.

        Returns (stdout, stderr, exit_code).
        Does NOT raise on non-zero exit codes — check exit_code yourself.
        Raises SynologySSHError if the transport itself fails.

        stdout/stderr are decoded UTF-8 with errors='replace'.
        """
        if self._client is None:
            raise SynologySSHError("Not connected. Call connect() or use as context manager.")
        try:
            stdin, stdout_obj, stderr_obj = self._client.exec_command(
                command, timeout=timeout or self._timeout
            )
            exit_code = stdout_obj.channel.recv_exit_status()
            stdout = stdout_obj.read().decode("utf-8", errors="replace")
            stderr = stderr_obj.read().decode("utf-8", errors="replace")
            return stdout, stderr, exit_code
        except SynologySSHError:
            raise
        except Exception as exc:
            raise SynologySSHError(f"Command execution failed: {exc}") from exc

    # ---- Docker operations via SSH ----

    def docker_exec(self, container: str, command: str) -> tuple[str, str, int]:
        """
        Run a command inside a running container. ⚠️ DESTRUCTIVE

        Before calling — confirmation gate (see SKILL.md):
        1. "This will run [command] inside container [container]."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.
        """
        return self.run(f"{self._docker_bin} exec {container} {command}")

    def docker_pull(self, image: str) -> tuple[str, str, int]:
        """
        Pull an image from a registry. ⚠️ DESTRUCTIVE — modifies local image store.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will pull image [image] onto the NAS."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.
        """
        return self.run(f"{self._docker_bin} pull {image}")

    def docker_build(
        self,
        context_path: str,
        tag: str,
        dockerfile: str | None = None,
    ) -> tuple[str, str, int]:
        """
        Build an image from a path on the NAS. ⚠️ DESTRUCTIVE — creates a new image.

        Before calling — confirmation gate (see SKILL.md):
        1. "This will build image [tag] from [context_path] on the NAS."
        2. Ask: "Confirm? (yes / no)"
        3. Wait for explicit 'yes'. Anything else → abort.

        context_path: absolute path on the NAS filesystem.
        """
        cmd = f"{self._docker_bin} build -t {tag}"
        if dockerfile:
            cmd += f" -f {dockerfile}"
        cmd += f" {context_path}"
        return self.run(cmd)

    def docker_logs(self, container: str, tail: int = 100) -> tuple[str, str, int]:
        """
        Get container logs via docker CLI. 🔵 SENSITIVE

        Before calling — intent declaration (see SKILL.md):
        "I'm going to read logs for container [container],
        which may contain passwords, tokens, or other sensitive output."

        Prefer this over ContainerManager.get_logs() — API logs are truncated.
        """
        return self.run(f"{self._docker_bin} logs --tail {tail} {container}")

    def docker_inspect(self, container: str) -> tuple[str, str, int]:
        """
        Get full container configuration via docker inspect. 🔵 SENSITIVE

        Before calling — intent declaration (see SKILL.md):
        "I'm going to inspect container [container].
        The output may include environment variables with credentials."
        """
        return self.run(f"{self._docker_bin} inspect {container}")


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def get_filestation() -> SynologyFileStation:
    """Create a connected FileStation client from environment variables."""
    return SynologyFileStation()


def get_downloadstation() -> SynologyDownloadStation:
    """Create a connected DownloadStation client from environment variables."""
    return SynologyDownloadStation()


def get_taskscheduler() -> SynologyTaskScheduler:
    """Create a connected TaskScheduler client from environment variables."""
    return SynologyTaskScheduler()


def get_container_manager() -> SynologyContainerManager:
    """Create a connected ContainerManager client from environment variables."""
    return SynologyContainerManager()


def get_ssh(timeout: int = 30) -> SynologySSH:
    """
    Create a SynologySSH instance (not yet connected).

    Raises SynologySSHNotAvailable if paramiko is not installed.
    Use as a context manager: with get_ssh() as ssh: ...
    """
    return SynologySSH(timeout=timeout)
