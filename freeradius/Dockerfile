# syntax=docker/dockerfile:1
# FreeRADIUS 3.2 with an embedded control agent.
#
# NOTE: build this in an environment with Docker Hub access. The control agent
# needs a minimal Python 3 runtime (stdlib only - no pip packages).
FROM freeradius/freeradius-server:3.2.5

# Minimal Python 3 for the control agent (no third-party packages required).
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

# Enable authentication logging to a file so the "Live Log" view has data,
# and make sure logs go to a file the agent can tail (spec section 13).
RUN sed -i \
      -e 's/^\(\s*\)destination = .*/\1destination = files/' \
      -e 's/^\(\s*\)auth = no/\1auth = yes/' \
      /etc/raddb/radiusd.conf

COPY control_agent/agent.py /opt/agent/agent.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# Runtime layout owned by the unprivileged 'freerad' user that ships in the base
# image. radiusd started by this same user does not need to setuid, so the
# container runs fully non-root (spec section 26).
ENV RADDB_DIR=/etc/raddb \
    RADIUS_LOG_FILE=/var/log/radius/radius.log \
    RADIUS_AGENT_PORT=8000
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && mkdir -p /var/log/radius /opt/agent \
 && printf '# Managed by FreeRADIUS Manager\n' > /etc/raddb/clients.conf \
 && touch /var/log/radius/radius.log \
 && chown -R freerad:freerad /etc/raddb /var/log/radius /opt/agent

USER freerad

# 1812/udp auth, 1813/udp accounting, 8000/tcp control agent (internal only).
EXPOSE 1812/udp 1813/udp 8000/tcp

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import urllib.request,sys; \
      sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else sys.exit(1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
