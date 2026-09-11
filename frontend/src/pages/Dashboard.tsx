import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import { api, errorMessage } from "../api/client";

interface DashboardData {
  radius: { reachable: boolean; running?: boolean; version?: string; error?: string };
  clients: { total: number; enabled: number; disabled: number };
  active_config_version: number | null;
  active_directory: { status: string; note: string };
  certificates: { status: string; note: string };
}

function StatCard({ title, value, sub }: { title: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="overline" color="text.secondary">
          {title}
        </Typography>
        <Typography variant="h4" sx={{ fontWeight: 700 }}>
          {value}
        </Typography>
        {sub && (
          <Typography variant="body2" color="text.secondary">
            {sub}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<DashboardData>("/dashboard")
      .then((r) => setData(r.data))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  if (error) return <Alert severity="error">{error}</Alert>;
  if (!data) return <CircularProgress />;

  const radiusOk = data.radius.reachable && data.radius.running !== false;

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3 }}>
        Dashboard
      </Typography>
      <Grid container spacing={3}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="overline" color="text.secondary">
                RADIUS Server
              </Typography>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1 }}>
                {radiusOk ? (
                  <CheckCircleIcon color="success" />
                ) : (
                  <ErrorIcon color="error" />
                )}
                <Typography variant="h6">
                  {radiusOk ? "Running" : "Unavailable"}
                </Typography>
              </Box>
              {data.radius.version && (
                <Typography variant="caption" color="text.secondary">
                  {data.radius.version}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="RADIUS Clients"
            value={`${data.clients.enabled} active`}
            sub={`${data.clients.disabled} disabled / ${data.clients.total} total`}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            title="Active Config"
            value={
              data.active_config_version ? `v${data.active_config_version}` : "none"
            }
            sub="Currently loaded by FreeRADIUS"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="overline" color="text.secondary">
                Active Directory
              </Typography>
              <Box sx={{ mt: 1 }}>
                <Chip label="Not configured" color="warning" size="small" />
              </Box>
              <Typography variant="caption" color="text.secondary">
                {data.active_directory.note}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Alert severity="info" sx={{ mt: 3 }}>
        Phase 1 &amp; 2 are active: local login, RADIUS client management, config
        generation, validation, reload and logs. Active Directory, policies,
        certificates and end-to-end authentication tests arrive in later phases.
      </Alert>
    </Box>
  );
}
