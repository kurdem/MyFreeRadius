import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Grid,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ScienceIcon from "@mui/icons-material/Science";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import { api, errorMessage } from "../api/client";

interface Result {
  result: string;
  duration_ms: number;
  details?: string | null;
  accepted: boolean;
}

export default function TestAuth() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  const run = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.post<Result>("/radius/test", { username, password });
      setResult(r.data);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 2 }}>
        Test Authentication
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        Sends a <b>real</b> RADIUS Access-Request through FreeRADIUS (the full
        pipeline: manager site → LDAP / MFA → Active Directory). The passcode is
        whatever your current mode expects: the AD password (LDAP mode), the OTP
        (MFA <code>totp_only</code>), or AD password + OTP (append mode).
        Passwords are never logged.
      </Alert>

      <Paper sx={{ p: 3, mb: 3, maxWidth: 560 }}>
        <Grid container spacing={2}>
          <Grid item xs={12}>
            <TextField label="Username" fullWidth value={username}
              onChange={(e) => setUsername(e.target.value)} autoFocus />
          </Grid>
          <Grid item xs={12}>
            <TextField label="Passcode" type="password" fullWidth value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && username && password && run()} />
          </Grid>
        </Grid>
        <Button
          variant="contained"
          startIcon={<ScienceIcon />}
          onClick={run}
          disabled={busy || !username || !password}
          sx={{ mt: 2 }}
        >
          {busy ? "Testing..." : "Test Authentication"}
        </Button>
      </Paper>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {result && (
        <Paper sx={{ p: 3, maxWidth: 720 }}>
          <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1 }}>
            {result.accepted ? (
              <CheckCircleIcon color="success" fontSize="large" />
            ) : (
              <CancelIcon color="error" fontSize="large" />
            )}
            <Typography variant="h6">{result.result}</Typography>
            <Chip label={`${result.duration_ms} ms`} size="small" />
          </Stack>
          {result.details && (
            <Box sx={{ mt: 1 }}>
              <Button size="small" onClick={() => setShowRaw((v) => !v)}>
                {showRaw ? "Hide" : "Show"} radclient output
              </Button>
              {showRaw && (
                <Box
                  component="pre"
                  sx={{ mt: 1, p: 2, bgcolor: "grey.900", color: "grey.100",
                        fontSize: 12, overflow: "auto", maxHeight: 360, borderRadius: 1 }}
                >
                  {result.details}
                </Box>
              )}
            </Box>
          )}
        </Paper>
      )}
    </Box>
  );
}
