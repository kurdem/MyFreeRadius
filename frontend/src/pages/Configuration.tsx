import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import BuildIcon from "@mui/icons-material/Build";
import CheckIcon from "@mui/icons-material/Check";
import PublishIcon from "@mui/icons-material/Publish";
import HistoryIcon from "@mui/icons-material/History";
import VisibilityIcon from "@mui/icons-material/Visibility";
import RestoreIcon from "@mui/icons-material/RestartAlt";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface Version {
  id: number;
  version: number;
  state: "pending" | "active" | "previous" | "failed";
  checksum: string;
  change_summary?: string | null;
  author?: string | null;
  created_at: string;
}

const stateColor: Record<Version["state"], "warning" | "success" | "default" | "error"> = {
  pending: "warning",
  active: "success",
  previous: "default",
  failed: "error",
};

export default function Configuration() {
  const { isAdmin } = useAuth();
  const [history, setHistory] = useState<Version[]>([]);
  const [pending, setPending] = useState<Version | null>(null);
  const [preview, setPreview] = useState<{ files: Record<string, string>; deletes: string[] } | null>(null);
  const [message, setMessage] = useState<{ severity: "success" | "error" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState<
    { version: Version; files: Record<string, string>; deletes: string[] } | null
  >(null);

  const loadHistory = () =>
    api.get<Version[]>("/configuration/history").then((r) => setHistory(r.data)).catch((e) => setMessage({ severity: "error", text: errorMessage(e) }));

  useEffect(() => {
    loadHistory();
  }, []);

  const generate = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await api.get<Version | null>("/configuration/pending");
      if (!r.data) {
        setMessage({ severity: "info", text: "No changes to apply." });
        setPending(null);
        setPreview(null);
      } else {
        setPending(r.data);
        const c = await api.get<{ files: Record<string, string>; deletes: string[] }>(
          `/configuration/${r.data.id}/content`,
        );
        setPreview({ files: c.data.files, deletes: c.data.deletes });
        if (r.data.state === "active") {
          setMessage({ severity: "info", text: "Current configuration already matches the database." });
        }
      }
      loadHistory();
    } catch (e) {
      setMessage({ severity: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const validate = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const r = await api.post<{ valid: boolean; message: string; details?: string }>(
        `/configuration/${pending.id}/validate`,
      );
      setMessage({
        severity: r.data.valid ? "success" : "error",
        text: r.data.valid ? "Configuration valid." : `Invalid: ${r.data.details ?? r.data.message}`,
      });
    } catch (e) {
      setMessage({ severity: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const activate = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      const r = await api.post<{ success: boolean; message: string; details?: string }>(
        `/configuration/${pending.id}/activate`,
      );
      setMessage({
        severity: r.data.success ? "success" : "error",
        text: r.data.success ? `Activated version ${pending.version}.` : r.data.details ?? r.data.message,
      });
      if (r.data.success) {
        setPending(null);
        setPreview(null);
      }
      loadHistory();
    } catch (e) {
      setMessage({ severity: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const rollback = async () => {
    if (!window.confirm("Roll back to the previous configuration?")) return;
    setBusy(true);
    try {
      const r = await api.post<{ success: boolean; version?: number }>("/configuration/rollback");
      setMessage({
        severity: r.data.success ? "success" : "error",
        text: r.data.success ? `Rolled back (new version ${r.data.version}).` : "Rollback failed.",
      });
      loadHistory();
    } catch (e) {
      setMessage({ severity: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const viewVersion = async (v: Version) => {
    setBusy(true);
    try {
      const c = await api.get<{ files: Record<string, string>; deletes: string[] }>(
        `/configuration/${v.id}/content`,
      );
      setViewing({ version: v, files: c.data.files, deletes: c.data.deletes });
    } catch (e) {
      setMessage({ severity: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const restoreVersion = async (v: Version) => {
    if (!window.confirm(`Activate configuration version ${v.version}? A new version is created from its content and applied to FreeRADIUS.`))
      return;
    setBusy(true);
    setMessage(null);
    try {
      const r = await api.post<{ success: boolean; version?: number; details?: string; message: string }>(
        `/configuration/${v.id}/restore`,
      );
      setMessage({
        severity: r.data.success ? "success" : "error",
        text: r.data.success
          ? `Restored version ${v.version} (new active version ${r.data.version}).`
          : r.data.details ?? r.data.message,
      });
      if (r.data.success) {
        setPending(null);
        setPreview(null);
      }
      loadHistory();
    } catch (e) {
      setMessage({ severity: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const deleteVersion = async (v: Version) => {
    if (!window.confirm(`Delete configuration version ${v.version}? This cannot be undone.`)) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.delete(`/configuration/${v.id}`);
      setMessage({ severity: "success", text: `Deleted version ${v.version}.` });
      loadHistory();
    } catch (e) {
      setMessage({ severity: "error", text: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 2 }}>
        Configuration
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        Workflow: <b>Generate</b> a candidate from the current clients, <b>Validate</b>{" "}
        its syntax with FreeRADIUS, then <b>Activate</b> to reload. A failed activation
        keeps the previous working configuration. In the history below you can{" "}
        <b>view</b> any version, <b>activate</b> an earlier one, or <b>delete</b> old
        versions (the active version is protected).
      </Alert>

      {message && (
        <Alert severity={message.severity} sx={{ mb: 2 }} onClose={() => setMessage(null)}>
          {message.text}
        </Alert>
      )}

      {isAdmin && (
        <Stack direction="row" spacing={2} sx={{ mb: 2 }} flexWrap="wrap">
          <Button variant="contained" startIcon={<BuildIcon />} onClick={generate} disabled={busy}>
            Generate Candidate
          </Button>
          <Button startIcon={<CheckIcon />} onClick={validate} disabled={busy || !pending}>
            Validate
          </Button>
          <Button
            variant="contained"
            color="success"
            startIcon={<PublishIcon />}
            onClick={activate}
            disabled={busy || !pending}
          >
            Activate
          </Button>
          <Button color="warning" startIcon={<HistoryIcon />} onClick={rollback} disabled={busy}>
            Rollback
          </Button>
        </Stack>
      )}

      {preview && (
        <Paper variant="outlined" sx={{ p: 2, mb: 3, bgcolor: "grey.900" }}>
          <Typography variant="overline" sx={{ color: "grey.400" }}>
            Candidate configuration (v{pending?.version})
          </Typography>
          {Object.entries(preview.files).map(([path, content]) => (
            <Box key={path} sx={{ mt: 1 }}>
              <Typography variant="caption" sx={{ color: "#90caf9" }}>
                {path}
              </Typography>
              <Box
                component="pre"
                sx={{ color: "grey.100", fontSize: 13, overflow: "auto", m: 0, mt: 0.5 }}
              >
                {content}
              </Box>
            </Box>
          ))}
          {preview.deletes.length > 0 && (
            <Typography variant="caption" sx={{ color: "#ef9a9a", display: "block", mt: 1 }}>
              Removed on activate: {preview.deletes.join(", ")}
            </Typography>
          )}
        </Paper>
      )}

      <Typography variant="h6" sx={{ mb: 1 }}>
        Configuration History
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Version</TableCell>
            <TableCell>State</TableCell>
            <TableCell>Author</TableCell>
            <TableCell>Change</TableCell>
            <TableCell>Created</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {history.map((v) => (
            <TableRow key={v.id} hover>
              <TableCell>v{v.version}</TableCell>
              <TableCell>
                <Chip size="small" label={v.state} color={stateColor[v.state]} />
              </TableCell>
              <TableCell>{v.author ?? "-"}</TableCell>
              <TableCell>{v.change_summary ?? "-"}</TableCell>
              <TableCell>{new Date(v.created_at).toLocaleString()}</TableCell>
              <TableCell align="right">
                <Tooltip title="View content">
                  <IconButton size="small" onClick={() => viewVersion(v)} disabled={busy}>
                    <VisibilityIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                {isAdmin && (
                  <Tooltip title={v.state === "active" ? "Already active" : "Activate this version"}>
                    <span>
                      <IconButton
                        size="small"
                        color="warning"
                        onClick={() => restoreVersion(v)}
                        disabled={busy || v.state === "active"}
                      >
                        <RestoreIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                )}
                {isAdmin && (
                  <Tooltip title={v.state === "active" ? "The active version cannot be deleted" : "Delete this version"}>
                    <span>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => deleteVersion(v)}
                        disabled={busy || v.state === "active"}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                )}
              </TableCell>
            </TableRow>
          ))}
          {history.length === 0 && (
            <TableRow>
              <TableCell colSpan={6}>
                <Typography color="text.secondary" sx={{ py: 2 }}>
                  No configuration versions yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={!!viewing} onClose={() => setViewing(null)} maxWidth="md" fullWidth>
        <DialogTitle>Configuration v{viewing?.version.version}</DialogTitle>
        <DialogContent dividers>
          {viewing &&
            Object.entries(viewing.files).map(([path, content]) => (
              <Box key={path} sx={{ mb: 2 }}>
                <Typography variant="caption" sx={{ color: "primary.main", fontWeight: 600 }}>
                  {path}
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    fontSize: 13,
                    overflow: "auto",
                    m: 0,
                    mt: 0.5,
                    p: 1.5,
                    borderRadius: 1,
                    bgcolor: "grey.900",
                    color: "grey.100",
                  }}
                >
                  {content}
                </Box>
              </Box>
            ))}
          {viewing && viewing.deletes.length > 0 && (
            <Typography variant="caption" color="error">
              Removed on activate: {viewing.deletes.join(", ")}
            </Typography>
          )}
          {viewing && Object.keys(viewing.files).length === 0 && (
            <Typography color="text.secondary">This version has no files.</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewing(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
