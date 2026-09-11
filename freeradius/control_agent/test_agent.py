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
            if grep -rq INVALID_MARKER "${RADDB_DIR:-/etc/raddb}" 2>/dev/null; then
              echo "Error: INVALID_MARKER found"; exit 1
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
    ok, details = ctrl.validate({"clients.conf": "client a {\n ipaddr=10.0.0.1\n secret=\"x\"\n}\n"})
    check("validate accepts good config", ok)

    # validate: bad config, and the on-disk config is restored afterwards
    ok, details = ctrl.validate({"clients.conf": "INVALID_MARKER\n"})
    check("validate rejects bad config", not ok)
    with open(os.path.join(raddb, "clients.conf")) as fh:
        check("validate restores previous config", fh.read() == "# initial\n")

    # secret masking in returned details
    ok, details = ctrl.validate({"clients.conf": 'client a {\n secret = supersecret\n}\n'})
    check("details mask secrets", "supersecret" not in details)

    # apply: good config gets written and process starts
    ok, details = ctrl.apply({"clients.conf": "client good {\n ipaddr=10.0.0.2\n secret=\"y\"\n}\n"})
    check("apply succeeds", ok)
    check("apply left radiusd running", ctrl.is_running())
    with open(os.path.join(raddb, "clients.conf")) as fh:
        check("apply wrote new config", "client good" in fh.read())

    # apply: invalid config is rejected and previous config preserved
    ok, details = ctrl.apply({"clients.conf": "INVALID_MARKER\n"})
    check("apply rejects invalid config", not ok)
    with open(os.path.join(raddb, "clients.conf")) as fh:
        check("invalid apply preserved good config", "client good" in fh.read())

    # multi-file apply: writes ldap module + manager site, removes default site
    os.makedirs(os.path.join(raddb, "sites-enabled"), exist_ok=True)
    with open(os.path.join(raddb, "sites-enabled", "default"), "w") as fh:
        fh.write("server default {}\n")
    ok, details = ctrl.apply(
        {
            "clients.conf": "client c {\n ipaddr=10.0.0.3\n secret=\"z\"\n}\n",
            "mods-enabled/ldap": "ldap { server = 'dc01' }\n",
            "sites-enabled/manager": "server manager {}\n",
        },
        deletes=["sites-enabled/default"],
    )
    check("multi-file apply succeeds", ok)
    check("ldap module written", os.path.exists(os.path.join(raddb, "mods-enabled", "ldap")))
    check("manager site written", os.path.exists(os.path.join(raddb, "sites-enabled", "manager")))
    check("default site removed", not os.path.exists(os.path.join(raddb, "sites-enabled", "default")))

    # invalid multi-file apply rolls the WHOLE bundle back (default restored)
    with open(os.path.join(raddb, "sites-enabled", "default"), "w") as fh:
        fh.write("server default {}\n")
    ok, _ = ctrl.apply(
        {"clients.conf": "client d {}\n", "sites-enabled/manager": "INVALID_MARKER\n"},
        deletes=["sites-enabled/default"],
    )
    check("invalid multi-file apply fails", not ok)
    check("rollback restored default site", os.path.exists(os.path.join(raddb, "sites-enabled", "default")))
    with open(os.path.join(raddb, "sites-enabled", "manager")) as fh:
        check("rollback restored manager site", "INVALID_MARKER" not in fh.read())

    # path-allow-list: writing outside the allow-list is rejected
    try:
        ctrl.validate({"../evil": "x"})
        check("path traversal rejected", False)
    except ValueError:
        check("path traversal rejected", True)

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
