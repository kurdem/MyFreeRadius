#!/usr/bin/env python3
"""FreeRADIUS control agent.

Runs *inside* the FreeRADIUS container and owns the ``radiusd`` process. The
management backend talks to it over the internal Docker network, authenticated
with a shared bearer token (``RADIUS_AGENT_TOKEN``).

Responsibilities (spec sections 3, 12, 13, 14, 15):

* start / restart the ``radiusd`` process;
* validate a candidate ``clients.conf`` with ``radiusd -XC`` WITHOUT disturbing
  the running server;
* apply a candidate: validate -> back up current -> write -> restart, rolling
  back to the previous config if the restart fails;
* expose masked log tails and process status.

Only the standard library is used so the image stays minimal. No untrusted
input is ever passed to a shell: subprocess is always called with an argument
list and ``shell=False``.
"""
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RADDB = os.environ.get("RADDB_DIR", "/etc/raddb")
CLIENTS_CONF = os.path.join(RADDB, "clients.conf")
LOG_FILE = os.environ.get("RADIUS_LOG_FILE", "/var/log/radius/radius.log")
AGENT_TOKEN = os.environ.get("RADIUS_AGENT_TOKEN", "")
AGENT_PORT = int(os.environ.get("RADIUS_AGENT_PORT", "8000"))

# The only files the backend is allowed to write/delete. This is a hard security
# boundary against path traversal: any path not in these sets is rejected.
ALLOWED_WRITE_PATHS = {
    "clients.conf",
    "mods-enabled/ldap",
    "mods-enabled/rest",
    "sites-enabled/manager",
    "mods-config/manager_authorize",
}
# Managed files we may remove when switching modes. We never touch the stock
# "default" site: clients are routed to the "manager" server via
# `virtual_server = manager` instead, so nothing needs deleting to stay safe.
ALLOWED_DELETE_PATHS = {
    "mods-enabled/ldap",
    "mods-enabled/rest",
    "sites-enabled/manager",
    "mods-config/manager_authorize",
}

# Mask anything that looks like a secret before it leaves the agent.
_SECRET_LINE_RE = re.compile(r"(?i)(secret\s*=\s*)(\S+)")


def _radiusd_binary() -> str:
    for candidate in ("radiusd", "freeradius"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("Neither 'radiusd' nor 'freeradius' found in PATH")


def mask(text: str) -> str:
    return _SECRET_LINE_RE.sub(r"\1***REDACTED***", text)


class RadiusController:
    """Serialised control of the radiusd process and its config file."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._binary = _radiusd_binary()
        # Live log ring buffer, fed from radiusd's own stdout/stderr. This is
        # independent of the on-disk log path/permissions, so the Live Log works
        # regardless of how radiusd is configured to log.
        self._log_buffer: collections.deque[str] = collections.deque(
            maxlen=int(os.environ.get("RADIUS_LOG_BUFFER", "5000"))
        )

    # -- process lifecycle -------------------------------------------------- #
    def start(self) -> None:
        with self._lock:
            self._start_locked()

    def _start_locked(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        # -f: foreground (we manage the process). We capture stdout+stderr and
        # fan it out to the ring buffer and the log file, so the Live Log always
        # has data even if file logging is misconfigured.
        self._proc = subprocess.Popen(
            [self._binary, "-f"],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        reader = threading.Thread(target=self._pump_output, args=(self._proc,), daemon=True)
        reader.start()

    def _pump_output(self, proc: subprocess.Popen) -> None:
        """Read radiusd output line by line into the buffer and the log file."""
        stream = proc.stdout
        if stream is None:
            return
        try:
            log_fh = open(LOG_FILE, "a", errors="replace")
        except OSError:
            log_fh = None
        try:
            for raw in stream:
                line = mask(raw.rstrip("\n"))
                self._log_buffer.append(line)
                if log_fh is not None:
                    try:
                        log_fh.write(line + "\n")
                        log_fh.flush()
                    except OSError:
                        pass
        finally:
            if log_fh is not None:
                log_fh.close()

    def _stop_locked(self, timeout: float = 10.0) -> None:
        if not self._proc:
            return
        if self._proc.poll() is None:
            self._proc.send_signal(signal.SIGTERM)
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        self._proc = None

    def _restart_locked(self) -> bool:
        self._stop_locked()
        self._start_locked()
        # Give radiusd a moment to bind sockets / fail fast.
        time.sleep(2.0)
        return self._proc is not None and self._proc.poll() is None

    def is_running(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    def status(self) -> dict:
        rc, out = self._run_check(["-v"])
        version = ""
        if rc == 0:
            first = out.strip().splitlines()[0] if out.strip() else ""
            version = first
        return {"running": self.is_running(), "version": version}

    # -- config validate / apply ------------------------------------------- #
    def _run_check(self, extra_args: list[str], timeout: float = 30.0) -> tuple[int, str]:
        try:
            result = subprocess.run(
                [self._binary, *extra_args],
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, (result.stdout or "") + (result.stderr or "")
        except subprocess.TimeoutExpired:
            return 1, "validation timed out"

    # -- bundle helpers ----------------------------------------------------- #
    @staticmethod
    def _safe_path(rel: str, allowed: set[str]) -> str:
        """Resolve ``rel`` against RADDB, rejecting anything not allow-listed."""
        if rel not in allowed:
            raise ValueError(f"path not allowed: {rel}")
        full = os.path.normpath(os.path.join(RADDB, rel))
        # Defence in depth: ensure we stay under RADDB.
        if not (full == RADDB or full.startswith(RADDB + os.sep)):
            raise ValueError(f"path escapes config dir: {rel}")
        return full

    def _snapshot(self, files: dict, deletes: list) -> dict:
        """Record current on-disk state for every affected path."""
        snap: dict[str, str | None] = {}
        for rel in files:
            full = self._safe_path(rel, ALLOWED_WRITE_PATHS)
            snap[full] = self._read_file(full) if os.path.exists(full) else None
        for rel in deletes:
            full = self._safe_path(rel, ALLOWED_DELETE_PATHS)
            snap[full] = self._read_file(full) if os.path.exists(full) else None
        return snap

    def _restore(self, snap: dict) -> None:
        for full, content in snap.items():
            if content is None:
                if os.path.exists(full):
                    os.remove(full)
            else:
                self._write_file(full, content)

    def _write_bundle(self, files: dict, deletes: list) -> None:
        for rel, content in files.items():
            full = self._safe_path(rel, ALLOWED_WRITE_PATHS)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            self._write_file(full, content)
        for rel in deletes:
            full = self._safe_path(rel, ALLOWED_DELETE_PATHS)
            if os.path.exists(full):
                os.remove(full)

    def validate(self, files: dict, deletes: list | None = None) -> tuple[bool, str]:
        """Validate a candidate bundle with ``-XC``, then restore current state.

        The running server is never disturbed: we write the candidate files,
        run the syntax check, and roll every file back to how it was.
        """
        deletes = deletes or []
        with self._lock:
            snap = self._snapshot(files, deletes)
            try:
                self._write_bundle(files, deletes)
                rc, out = self._run_check(["-XC"])
            finally:
                self._restore(snap)
            return rc == 0, mask(out)

    def apply(self, files: dict, deletes: list | None = None) -> tuple[bool, str]:
        deletes = deletes or []
        with self._lock:
            snap = self._snapshot(files, deletes)
            try:
                # 1. Validate the whole bundle first.
                self._write_bundle(files, deletes)
                rc, out = self._run_check(["-XC"])
                if rc != 0:
                    self._restore(snap)
                    return False, "Validation failed:\n" + mask(out)

                # 2. Reload (restart) with the new bundle in place.
                ok = self._restart_locked()
                if ok:
                    return True, "Configuration applied and FreeRADIUS reloaded."

                # 3. Reload failed -> roll the whole bundle back and restart.
                self._restore(snap)
                self._restart_locked()
                return False, "Reload failed; rolled back to the previous configuration."
            except Exception:
                # Any error mid-write (e.g. permissions) -> restore the snapshot
                # so we never leave a half-written bundle behind, then re-raise
                # for the HTTP layer to report.
                self._restore(snap)
                raise

    # -- logs --------------------------------------------------------------- #
    def tail_log(self, limit: int) -> dict:
        # Prefer the in-memory buffer (captured from radiusd's own output).
        if self._log_buffer:
            lines = list(self._log_buffer)[-limit:]
            return {"lines": lines, "count": len(lines)}
        # Fall back to the log file if the buffer is empty (e.g. just started).
        try:
            with open(LOG_FILE, "r", errors="replace") as fh:
                file_lines = [mask(x.rstrip("\n")) for x in fh.readlines()[-limit:]]
            if file_lines:
                return {"lines": file_lines, "count": len(file_lines)}
        except FileNotFoundError:
            pass
        # Nothing yet: return a hint instead of an empty view so the UI is clear.
        hint = (
            "No RADIUS log output yet. FreeRADIUS "
            + ("is running" if self.is_running() else "is NOT running")
            + "; lines appear here once it logs activity (e.g. an Access-Request)."
        )
        return {"lines": [hint], "count": 1}

    # -- file helpers ------------------------------------------------------- #
    @staticmethod
    def _read_file(path: str) -> str:
        try:
            with open(path, "r") as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    @staticmethod
    def _write_file(path: str, content: str) -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "w") as fh:
            fh.write(content)
        os.replace(tmp, path)


controller = RadiusController()


class Handler(BaseHTTPRequestHandler):
    server_version = "radius-control-agent/0.2"

    def _authorized(self) -> bool:
        if not AGENT_TOKEN:
            return False
        header = self.headers.get("Authorization", "")
        return header == f"Bearer {AGENT_TOKEN}"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode())
        except (ValueError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt, *args):  # noqa: A003 - silence default stderr logging
        return

    def do_GET(self):  # noqa: N802
        # /health is unauthenticated for container healthchecks; it reveals nothing.
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        if not self._authorized():
            return self._send(401, {"detail": "unauthorized"})
        if self.path == "/status":
            return self._send(200, controller.status())
        if self.path.startswith("/logs"):
            limit = 200
            if "?" in self.path:
                query = self.path.split("?", 1)[1]
                for part in query.split("&"):
                    if part.startswith("limit="):
                        try:
                            limit = max(1, min(2000, int(part.split("=", 1)[1])))
                        except ValueError:
                            pass
            return self._send(200, controller.tail_log(limit))
        return self._send(404, {"detail": "not found"})

    def _bundle_from_body(self, body: dict) -> tuple[dict, list] | None:
        """Accept either a full bundle {files, deletes} or legacy {clients_conf}."""
        if isinstance(body.get("files"), dict):
            files = body["files"]
            deletes = body.get("deletes") or []
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
                return None
            if not all(isinstance(d, str) for d in deletes):
                return None
            return files, deletes
        candidate = body.get("clients_conf")
        if isinstance(candidate, str):
            return {"clients.conf": candidate}, []
        return None

    def do_POST(self):  # noqa: N802
        if not self._authorized():
            return self._send(401, {"detail": "unauthorized"})
        body = self._read_json()
        bundle = self._bundle_from_body(body)
        if bundle is None:
            return self._send(400, {"detail": "files (object) or clients_conf (string) required"})
        files, deletes = bundle
        try:
            if self.path == "/config/validate":
                valid, details = controller.validate(files, deletes)
                return self._send(200, {
                    "valid": valid,
                    "message": "Configuration valid" if valid else "Configuration invalid",
                    "details": details,
                })
            if self.path == "/config/apply":
                success, details = controller.apply(files, deletes)
                return self._send(200, {
                    "success": success,
                    "message": details.splitlines()[0] if details else "",
                    "details": details,
                })
        except ValueError as exc:
            # Rejected path (allow-list violation) etc.
            return self._send(400, {"detail": mask(str(exc))})
        except Exception as exc:  # noqa: BLE001 - never drop the connection
            # e.g. PermissionError writing config. Return a readable error to the
            # UI instead of disconnecting, and keep the agent serving.
            return self._send(500, {"detail": mask(f"{type(exc).__name__}: {exc}")})
        return self._send(404, {"detail": "not found"})


def main() -> None:
    if not AGENT_TOKEN:
        raise SystemExit("RADIUS_AGENT_TOKEN must be set")
    controller.start()
    httpd = ThreadingHTTPServer(("0.0.0.0", AGENT_PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
