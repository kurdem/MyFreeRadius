import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import { api, errorMessage } from "../api/client";

interface Component {
  name: string;
  status: "OK" | "WARNING" | "CRITICAL";
  detail?: string | null;
}

interface DetailedHealth {
  status: "OK" | "WARNING" | "CRITICAL";
  components: Component[];
}

const STATUS_COLOR: Record<string, "success" | "warning" | "error"> = {
  OK: "success",
  WARNING: "warning",
  CRITICAL: "error",
};

export default function Monitoring() {
  const [health, setHealth] = useState<DetailedHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get<DetailedHealth>("/health/detailed");
      setHealth(r.data);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <MonitorHeartIcon />
        <Typography variant="h4" sx={{ flexGrow: 1 }}>
          Monitoring
        </Typography>
        <Button startIcon={<RefreshIcon />} onClick={load} disabled={loading}>
          Refresh
        </Button>
      </Stack>

      <Alert severity="info" sx={{ mb: 2 }}>
        Live component health. Prometheus metrics are exposed at{" "}
        <code>/metrics</code> and can be scraped with the optional monitoring
        profile (<code>docker compose --profile monitoring up -d</code>) — see{" "}
        <code>docs/monitoring.md</code>.
      </Alert>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper sx={{ p: 3 }}>
        {loading && !health ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress />
          </Box>
        ) : health ? (
          <>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
              <Typography variant="h6">Overall status</Typography>
              <Chip
                label={health.status}
                color={STATUS_COLOR[health.status] ?? "default"}
              />
            </Stack>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Component</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Detail</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {health.components.map((c) => (
                  <TableRow key={c.name}>
                    <TableCell sx={{ textTransform: "capitalize" }}>
                      {c.name.replace(/_/g, " ")}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={c.status}
                        color={STATUS_COLOR[c.status] ?? "default"}
                      />
                    </TableCell>
                    <TableCell>{c.detail ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        ) : null}
      </Paper>
    </Box>
  );
}
