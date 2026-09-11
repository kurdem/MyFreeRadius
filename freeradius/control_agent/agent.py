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
PREVIOUS_CONF = os.path.join(RADDB, "clients.conf.previous")
LOG_FILE = os.environ.get("RADIUS_LOG_FILE", "/var/log/radius/radius.log")
AGENT_TOKEN = os.environ.get("RADIUS_AGENT_TOKEN", "")
AGENT_PORT = int(os.environ.get("RADIUS_AGENT_PORT", "8000"))

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

    def validate(self, candidate: str) -> tuple[bool, str]:
        """Validate ``candidate`` with ``radiusd -XC`` and restore current config."""
        with self._lock:
            current = self._read_file(CLIENTS_CONF)
            try:
                self._write_file(CLIENTS_CONF, candidate)
                rc, out = self._run_check(["-XC"])
            finally:
                # Always restore the previously on-disk config; the running
                # server is untouched either way.
                self._write_file(CLIENTS_CONF, current)
            return rc == 0, mask(out)

    def apply(self, candidate: str) -> tuple[bool, str]:
        with self._lock:
            # 1. Validate first.
            current = self._read_file(CLIENTS_CONF)
            self._write_file(CLIENTS_CONF, candidate)
            rc, out = self._run_check(["-XC"])
            if rc != 0:
                self._write_file(CLIENTS_CONF, current)
                return False, "Validation failed:\n" + mask(out)

            # 2. Back up the known-good config, then reload (restart).
            if current:
                self._write_file(PREVIOUS_CONF, current)
            ok = self._restart_locked()
            if ok:
                return True, "Configuration applied and FreeRADIUS reloaded."

            # 3. Reload failed -> roll back to the previous config.
            self._write_file(CLIENTS_CONF, current)
            self._restart_locked()
            return False, "Reload failed; rolled back to the previous configuration."

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

    def do_POST(self):  # noqa: N802
        if not self._authorized():
            return self._send(401, {"detail": "unauthorized"})
        body = self._read_json()
        candidate = body.get("clients_conf")
        if not isinstance(candidate, str):
            return self._send(400, {"detail": "clients_conf (string) required"})
        if self.path == "/config/validate":
            valid, details = controller.validate(candidate)
            return self._send(200, {
                "valid": valid,
                "message": "Configuration valid" if valid else "Configuration invalid",
                "details": details,
            })
        if self.path == "/config/apply":
            success, details = controller.apply(candidate)
            return self._send(200, {
                "success": success,
                "message": details.splitlines()[0] if details else "",
                "details": details,
            })
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
