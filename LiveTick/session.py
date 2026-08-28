from __future__ import annotations

import atexit
import json
import os
import subprocess
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = ROOT / "Runtime"


class RuntimeSessionError(RuntimeError):
    pass


def now_text() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def runtime_dir(path: str | Path = DEFAULT_RUNTIME_DIR) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def session_file(name: str, session_dir: str | Path = DEFAULT_RUNTIME_DIR) -> Path:
    return runtime_dir(session_dir) / f"{_clean_name(name)}.json"


def stop_request_file(name: str, session_dir: str | Path = DEFAULT_RUNTIME_DIR) -> Path:
    return runtime_dir(session_dir) / f"{_clean_name(name)}.stop"


def request_stop(
    name: str, session_dir: str | Path = DEFAULT_RUNTIME_DIR, reason: str = "user_request"
) -> Path:
    path = stop_request_file(name, session_dir)
    payload = {
        "name": _clean_name(name),
        "requested_at": now_text(),
        "reason": reason,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_session(name: str, session_dir: str | Path = DEFAULT_RUNTIME_DIR) -> dict[str, Any] | None:
    path = session_file(name, session_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"name": _clean_name(name), "status": "corrupt", "path": str(path)}


def is_pid_running(pid: int | str | None) -> bool:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False
    if pid_int == os.getpid():
        return True

    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid_int}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        output = result.stdout.strip()
        return bool(output and "No tasks are running" not in output and str(pid_int) in output)

    try:
        os.kill(pid_int, 0)
    except OSError:
        return False
    return True


class RuntimeSession:
    def __init__(
        self,
        name: str,
        *,
        session_dir: str | Path = DEFAULT_RUNTIME_DIR,
        metadata: dict[str, Any] | None = None,
        heartbeat_seconds: int = 10,
        on_stop_requested: Callable[[], None] | None = None,
    ) -> None:
        self.name = _clean_name(name)
        self.session_dir = runtime_dir(session_dir)
        self.path = session_file(self.name, self.session_dir)
        self.stop_path = stop_request_file(self.name, self.session_dir)
        self.metadata = metadata or {}
        self.heartbeat_seconds = max(1, int(heartbeat_seconds))
        self.on_stop_requested = on_stop_requested
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._watcher_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._active = False

    def __enter__(self) -> RuntimeSession:
        self.start()
        return self

    def __exit__(self, exc_type, _exc, _tb) -> None:
        status = "error" if exc_type else "stopped"
        self.finish(status=status)

    def start(self) -> None:
        existing = load_session(self.name, self.session_dir)
        if existing and is_pid_running(existing.get("pid")):
            raise RuntimeSessionError(
                f"{self.name} is already running with PID {existing.get('pid')} "
                f"(started_at={existing.get('started_at')})."
            )

        if self.stop_path.exists():
            self.stop_path.unlink()

        self._active = True
        self._write(
            status="running",
            extra={
                "started_at": now_text(),
                "pid": os.getpid(),
                "metadata": self.metadata,
            },
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"{self.name}-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()

        self._watcher_thread = threading.Thread(
            target=self._stop_request_loop,
            name=f"{self.name}-stop-watcher",
            daemon=True,
        )
        self._watcher_thread.start()
        atexit.register(self.finish)

    def update(self, *, status: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        extra: dict[str, Any] = {}
        if metadata is not None:
            self.metadata.update(metadata)
            extra["metadata"] = self.metadata
        self._write(status=status, extra=extra)

    def finish(self, status: str = "stopped") -> None:
        if not self._active:
            return
        self._active = False
        self._stop_event.set()
        self._write(status=status, extra={"stopped_at": now_text()})
        try:
            if self.stop_path.exists():
                self.stop_path.unlink()
        except OSError:
            pass

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self.heartbeat_seconds):
            self._write(status="running")

    def _stop_request_loop(self) -> None:
        while not self._stop_event.wait(1):
            if not self.stop_path.exists():
                continue
            self._write(status="stop_requested")
            if self.on_stop_requested is not None:
                self.on_stop_requested()
            return

    def _write(self, *, status: str | None = None, extra: dict[str, Any] | None = None) -> None:
        with self._lock:
            current = load_session(self.name, self.session_dir) or {}
            current.update(
                {
                    "name": self.name,
                    "pid": os.getpid(),
                    "status": status or current.get("status", "running"),
                    "heartbeat_at": now_text(),
                }
            )
            if extra:
                current.update(_jsonable(extra))
            tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(current, indent=2, default=str), encoding="utf-8")
            tmp_path.replace(self.path)


def _clean_name(name: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in str(name).strip().lower()
    )
    if not cleaned:
        raise ValueError("session name cannot be empty")
    return cleaned


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_jsonable(item) for item in value]
        return str(value)
