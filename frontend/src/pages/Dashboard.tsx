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
import { Link as RouterLink } from "react-router-dom";
import Button from "@mui/material/Button";
import { api, errorMessage } from "../api/client";

interface DashboardData {
  radius: { reachable: boolean; running?: boolean; version?: string; error?: string };
  clients: { total: number; enabled: number; disabled: number };
  active_config_version: number | null;
  active_directory: { status: string; note: string; domain?: string };
  certificates: { status: string; note?: string };
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
  const [setupDone, setSetupDone] = useState(true);

  useEffect(() => {
    api
      .get<DashboardData>("/dashboard")
      .then((r) => setData(r.data))
      .catch((e) => setError(errorMessage(e)));
    api
      .get<{ setup_completed: boolean }>("/setup/status")
      .then((r) => setSetupDone(r.data.setup_completed))
      .catch(() => undefined);
  }, []);

  if (error) return <Alert severity="error">{error}</Alert>;
  if (!data) return <CircularProgress />;

  const radiusOk = data.radius.reachable && data.radius.running !== false;

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3 }}>
        Dashboard
      </Typography>
      {!setupDone && (
        <Alert
          severity="info"
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small" component={RouterLink} to="/wizard">
              Open wizard
            </Button>
          }
        >
          Initial setup is not complete. Run the Setup Wizard to configure Active
          Directory, add a Horizon Connection Server, and activate the configuration.
        </Alert>
      )}
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
                {(() => {
                  const s = data.active_directory.status;
                  const label = s === "configured" ? "Connected"
                    : s === "disabled" ? "Configured (disabled)"
                    : "Not configured";
                  const color = s === "configured" ? "success"
                    : s === "disabled" ? "default" : "warning";
                  return <Chip label={label} color={color} size="small" />;
                })()}
              </Box>
              <Typography variant="caption" color="text.secondary">
                {data.active_directory.domain
                  ? data.active_directory.domain
                  : data.active_directory.note}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Alert severity="info" sx={{ mt: 3 }}>
        Manage RADIUS clients, Active Directory, MFA, certificates and the
        configuration lifecycle from the menu. Use Test Auth to verify a login
        end-to-end, and Backup to export the configuration.
      </Alert>
    </Box>
  );
}
