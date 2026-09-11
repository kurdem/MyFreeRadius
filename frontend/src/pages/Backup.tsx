import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  Grid,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import RestoreIcon from "@mui/icons-material/Restore";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export default function Backup() {
  const { isAdmin } = useAuth();
  const [exportPass, setExportPass] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [restorePass, setRestorePass] = useState("");
  const [force, setForce] = useState(false);
  const [msg, setMsg] = useState<{ s: "success" | "error" | "info"; t: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const createBackup = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.post("/backup/export", { passphrase: exportPass || null },
        { responseType: "blob" });
      const cd: string = r.headers["content-disposition"] || "";
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m ? m[1] : "freeradius-manager-backup.json";
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      setMsg({ s: "success", t: `Backup downloaded (${filename}).` });
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const restore = async () => {
    if (!file) return;
    if (!window.confirm(
      "Restore will REPLACE all current configuration (clients, groups, AD, MFA " +
      "tokens, certificates, users) with the backup. Continue?")) return;
    setBusy(true);
    setMsg(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("passphrase", restorePass);
      form.append("force", String(force));
      const r = await api.post<{ message: string; restored: Record<string, number> }>(
        "/backup/restore", form);
      const counts = Object.entries(r.data.restored).map(([k, v]) => `${k}: ${v}`).join(", ");
      setMsg({ s: "success", t: `${r.data.message}\nRestored — ${counts}` });
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 2 }}>
        Backup &amp; Restore
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        A backup contains the full configuration (RADIUS clients, groups, Active
        Directory, MFA tokens, certificates, local users). Secrets are included
        <b> encrypted with the server key</b> — a backup only restores on a server
        with the same <code>FERNET_KEY</code>. Optionally protect the whole file
        with a passphrase. The audit log and config-version history are not included.
      </Alert>

      {msg && (
        <Alert severity={msg.s} sx={{ mb: 2, whiteSpace: "pre-wrap" }} onClose={() => setMsg(null)}>
          {msg.t}
        </Alert>
      )}

      <Paper sx={{ p: 3, mb: 3, maxWidth: 640 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>Create backup</Typography>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={7}>
            <TextField label="Passphrase (optional)" type="password" fullWidth
              value={exportPass} onChange={(e) => setExportPass(e.target.value)}
              helperText="If set, the backup file is encrypted with this passphrase." />
          </Grid>
          <Grid item xs={12} sm={5}>
            <Button variant="contained" startIcon={<DownloadIcon />} onClick={createBackup}
              disabled={busy}>
              Download backup
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {isAdmin && (
        <Paper sx={{ p: 3, maxWidth: 640 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>Restore backup</Typography>
          <Alert severity="warning" sx={{ mb: 2 }}>
            Destructive: replaces all current configuration. After restoring, go to
            Configuration → Generate → Activate to apply it to FreeRADIUS. You may
            need to log in again.
          </Alert>
          <Stack spacing={2}>
            <Button variant="outlined" component="label">
              {file ? `Selected: ${file.name}` : "Choose backup file"}
              <input type="file" hidden accept=".json,application/json,application/octet-stream"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Button>
            <TextField label="Passphrase (if the backup is encrypted)" type="password"
              value={restorePass} onChange={(e) => setRestorePass(e.target.value)} />
            <FormControlLabel
              control={<Checkbox checked={force} onChange={(e) => setForce(e.target.checked)} />}
              label="Force restore even if the FERNET_KEY differs (secrets will be unusable)"
            />
            <Box>
              <Button variant="contained" color="warning" startIcon={<RestoreIcon />}
                onClick={restore} disabled={busy || !file}>
                Restore
              </Button>
            </Box>
          </Stack>
        </Paper>
      )}
    </Box>
  );
}
