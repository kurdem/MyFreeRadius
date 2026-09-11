"""Standalone tests for the control agent logic (no real FreeRADIUS needed).

Run:  python3 test_agent.py
A fake ``radiusd`` script simulates ``-XC`` validation and ``-f`` startup so we
can exercise validate / apply / rollback / log tailing without pulling images.
"""
from __future__ import annotations

import importlib
import os
import stat
import sys
import tempfile
import textwrap


def _make_fake_radiusd(bindir: str) -> None:
    """A fake radiusd: `-XC` fails if the clients.conf holds INVALID_MARKER."""
    script = textwrap.dedent(
        """\
        #!/usr/bin/env bash
        MODE="$1"
        CONF="${RADDB_DIR:-/etc/raddb}/clients.conf"
        case "$MODE" in
          -v) echo "FreeRADIUS Version 3.2.x (fake)"; exit 0 ;;
          -XC)
            if grep -q INVALID_MARKER "$CONF" 2>/dev/null; then
              echo "Error: INVALID_MARKER on line 1"; exit 1
            fi
            echo "Configuration appears to be OK"; exit 0 ;;
          -f)
            echo "Listening on auth address * port 1812"
            echo "Ready to process requests"
            echo "Login OK: [max.mustermann] secret = supersecret"
            exec sleep 3600 ;;
          *) exit 0 ;;
        esac
        """
    )
    path = os.path.join(bindir, "radiusd")
    with open(path, "w") as fh:
        fh.write(script)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def main() -> int:
    tmp = tempfile.mkdtemp()
    raddb = os.path.join(tmp, "raddb")
    bindir = os.path.join(tmp, "bin")
    os.makedirs(raddb)
    os.makedirs(bindir)
    with open(os.path.join(raddb, "clients.conf"), "w") as fh:
        fh.write("# initial\n")

    _make_fake_radiusd(bindir)
    os.environ["PATH"] = bindir + os.pathsep + os.environ["PATH"]
    os.environ["RADDB_DIR"] = raddb
    os.environ["RADIUS_LOG_FILE"] = os.path.join(tmp, "radius.log")
    os.environ["RADIUS_AGENT_TOKEN"] = "test-token"

    agent = importlib.import_module("agent")
    ctrl = agent.RadiusController()

    failures = []

    def check(name, cond):
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    # validate: good config
    ok, details = ctrl.validate("client a {\n ipaddr=10.0.0.1\n secret=\"x\"\n}\n")
    check("validate accepts good config", ok)

    # validate: bad config, and the on-disk config is restored afterwards
    ok, details = ctrl.validate("INVALID_MARKER\n")
    check("validate rejects bad config", not ok)
    with open(os.path.join(raddb, "clients.conf")) as fh:
        check("validate restores previous config", fh.read() == "# initial\n")

    # secret masking in returned details
    ok, details = ctrl.validate('client a {\n secret = supersecret\n}\n')
    check("details mask secrets", "supersecret" not in details)

    # apply: good config gets written and process starts
    ok, details = ctrl.apply("client good {\n ipaddr=10.0.0.2\n secret=\"y\"\n}\n")
    check("apply succeeds", ok)
    check("apply left radiusd running", ctrl.is_running())
    with open(os.path.join(raddb, "clients.conf")) as fh:
        check("apply wrote new config", "client good" in fh.read())

    # apply: invalid config is rejected and previous config preserved
    ok, details = ctrl.apply("INVALID_MARKER\n")
    check("apply rejects invalid config", not ok)
    with open(os.path.join(raddb, "clients.conf")) as fh:
        check("invalid apply preserved good config", "client good" in fh.read())

    # live log: radiusd stdout is captured into the ring buffer
    import time as _t
    _t.sleep(0.5)  # let the reader thread drain the fake's stdout
    result = ctrl.tail_log(50)
    check("live log captured radiusd stdout",
          any("Ready to process requests" in ln for ln in result["lines"]))
    check("live log masks secrets in captured output",
          all("supersecret" not in ln for ln in result["lines"]))

    # file-fallback tailing + masking (buffer takes precedence, so test via a
    # fresh controller whose process has not produced output yet)
    with open(os.environ["RADIUS_LOG_FILE"], "a") as fh:
        fh.write("secret = leaked\n")
    fresh = agent.RadiusController()
    result = fresh.tail_log(10)
    check("file fallback masks secrets", all("leaked" not in ln for ln in result["lines"]))

    ctrl._stop_locked()

    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
