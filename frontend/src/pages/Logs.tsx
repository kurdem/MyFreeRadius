import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
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

export default function Logs() {
  const [tab, setTab] = useState(0);
  const [radiusLines, setRadiusLines] = useState<string[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
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

  useEffect(() => {
    if (tab === 0) loadRadius();
    else loadAudit();
  }, [tab, loadRadius, loadAudit]);

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
