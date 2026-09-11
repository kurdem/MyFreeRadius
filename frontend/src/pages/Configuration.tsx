import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import BuildIcon from "@mui/icons-material/Build";
import CheckIcon from "@mui/icons-material/Check";
import PublishIcon from "@mui/icons-material/Publish";
import HistoryIcon from "@mui/icons-material/History";
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

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 2 }}>
        Configuration
      </Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        Workflow: <b>Generate</b> a candidate from the current clients, <b>Validate</b>{" "}
        its syntax with FreeRADIUS, then <b>Activate</b> to reload. A failed activation
        keeps the previous working configuration.
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
            </TableRow>
          ))}
          {history.length === 0 && (
            <TableRow>
              <TableCell colSpan={5}>
                <Typography color="text.secondary" sx={{ py: 2 }}>
                  No configuration versions yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Box>
  );
}
