#!/bin/sh
# Entrypoint for the FreeRADIUS + control-agent container.
#
# The control agent is the container's main process; it starts and supervises
# radiusd as a child (see control_agent/agent.py). This keeps a single, well
# defined place that owns the radiusd lifecycle for validate/reload/rollback.
set -eu

# Ensure a clients.conf exists so radiusd's $INCLUDE never fails on first boot.
if [ ! -f /etc/raddb/clients.conf ]; then
    printf '# Managed by FreeRADIUS Manager - no clients yet.\n' > /etc/raddb/clients.conf
fi

# Ensure the log file exists and is tailable.
mkdir -p "$(dirname "${RADIUS_LOG_FILE:-/var/log/radius/radius.log}")"
: > "${RADIUS_LOG_FILE:-/var/log/radius/radius.log}" 2>/dev/null || true

exec python3 /opt/agent/agent.py
