import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { api, errorMessage } from "../api/client";

interface AuditRow {
  timestamp: string;
  username?: string | null;
  action: string;
  object?: string | null;
  source_ip?: string | null;
  result: string;
}

interface AuthEvent {
  timestamp: string;
  username?: string | null;
  source: string;
  result: string;
  reason?: string | null;
  source_ip?: string | null;
}

export default function Logs() {
  const [tab, setTab] = useState(0);
  const [radiusLines, setRadiusLines] = useState<string[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [authEvents, setAuthEvents] = useState<AuthEvent[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadRadius = useCallback(() => {
    api
      .get<{ lines: string[] }>("/logs/radius", { params: { limit: 300 } })
      .then((r) => setRadiusLines(r.data.lines))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  const loadAudit = useCallback(() => {
    api
      .get<AuditRow[]>("/logs/audit", { params: { limit: 300 } })
      .then((r) => setAudit(r.data))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  const loadAuthEvents = useCallback(() => {
    api
      .get<AuthEvent[]>("/logs/auth-events", { params: { limit: 300 } })
      .then((r) => setAuthEvents(r.data))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    if (tab === 0) loadRadius();
    else if (tab === 1) loadAuthEvents();
    else loadAudit();
  }, [tab, loadRadius, loadAuthEvents, loadAudit]);

  const shownLines = radiusLines.filter((l) => l.toLowerCase().includes(filter.toLowerCase()));

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 2 }}>
        Logs
      </Typography>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="RADIUS Live Log" />
        <Tab label="Authentication" />
        <Tab label="Audit Log" />
      </Tabs>

      {tab === 0 && (
        <Box>
          <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
            <TextField
              size="small"
              label="Filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Access-Accept, username, client..."
            />
            <Button startIcon={<RefreshIcon />} onClick={loadRadius}>
              Refresh
            </Button>
          </Stack>
          <Paper variant="outlined" sx={{ p: 2, bgcolor: "grey.900" }}>
            <Box
              component="pre"
              sx={{ color: "grey.100", fontSize: 13, m: 0, maxHeight: 500, overflow: "auto" }}
            >
              {shownLines.length ? shownLines.join("\n") : "No log lines."}
            </Box>
          </Paper>
          <Typography variant="caption" color="text.secondary">
            Secrets are masked automatically by the FreeRADIUS control agent.
          </Typography>
        </Box>
      )}

      {tab === 1 && (
        <Box>
          <Button startIcon={<RefreshIcon />} onClick={loadAuthEvents} sx={{ mb: 1 }}>
            Refresh
          </Button>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Authentication attempts with the reason a login was rejected (MFA / AD).
          </Typography>
          <Paper variant="outlined">
            <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr>
                  {["Time", "User", "Source", "Result", "Reason", "Source IP"].map((h) => (
                    <Box key={h} component="th"
                      sx={{ textAlign: "left", p: 1, borderBottom: "1px solid #ddd" }}>{h}</Box>
                  ))}
                </tr>
              </thead>
              <tbody>
                {authEvents.map((r, i) => (
                  <tr key={i}>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>
                      {new Date(r.timestamp).toLocaleString()}
                    </Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.username ?? "-"}</Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.source}</Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>
                      <Chip size="small" label={r.result}
                        color={r.result === "SUCCESS" ? "success" : "error"} />
                    </Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.reason ?? "-"}</Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.source_ip ?? "-"}</Box>
                  </tr>
                ))}
              </tbody>
            </Box>
          </Paper>
          {authEvents.length === 0 && (
            <Typography color="text.secondary" sx={{ py: 2 }}>
              No authentication attempts recorded yet.
            </Typography>
          )}
        </Box>
      )}

      {tab === 2 && (
        <Box>
          <Button startIcon={<RefreshIcon />} onClick={loadAudit} sx={{ mb: 1 }}>
            Refresh
          </Button>
          <Paper variant="outlined">
            <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr>
                  {["Time", "User", "Action", "Object", "Source IP", "Result"].map((h) => (
                    <Box
                      key={h}
                      component="th"
                      sx={{ textAlign: "left", p: 1, borderBottom: "1px solid #ddd" }}
                    >
                      {h}
                    </Box>
                  ))}
                </tr>
              </thead>
              <tbody>
                {audit.map((r, i) => (
                  <tr key={i}>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>
                      {new Date(r.timestamp).toLocaleString()}
                    </Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.username ?? "-"}</Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.action}</Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.object ?? "-"}</Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.source_ip ?? "-"}</Box>
                    <Box component="td" sx={{ p: 1, borderBottom: "1px solid #eee" }}>{r.result}</Box>
                  </tr>
                ))}
              </tbody>
            </Box>
          </Paper>
        </Box>
      )}
    </Box>
  );
}
