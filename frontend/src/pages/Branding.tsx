import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import SaveIcon from "@mui/icons-material/Save";
import { api, errorMessage } from "../api/client";

export default function Branding() {
  const [title, setTitle] = useState("");
  const [hasLogo, setHasLogo] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<{ s: "success" | "error"; t: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.get<{ app_title: string; has_logo: boolean }>("/branding").then((r) => {
      setTitle(r.data.app_title);
      setHasLogo(r.data.has_logo);
    });

  useEffect(() => {
    load().catch(() => undefined);
  }, []);

  const save = async (removeLogo = false) => {
    setBusy(true);
    setMsg(null);
    try {
      const form = new FormData();
      form.append("app_title", title);
      if (removeLogo) form.append("remove_logo", "true");
      else if (file) form.append("logo", file);
      await api.put("/branding", form);
      setMsg({ s: "success", t: "Branding saved. Reloading…" });
      // Reload so the app bar / login pick up the new logo and title.
      setTimeout(() => window.location.reload(), 600);
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
      setBusy(false);
    }
  };

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 2 }}>Branding</Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        Set a custom application title and logo. They appear in the top bar and on
        the login page. Upload your own logo (PNG, JPEG, GIF, WEBP or SVG, max 2 MB).
      </Alert>
      {msg && <Alert severity={msg.s} sx={{ mb: 2 }}>{msg.t}</Alert>}

      <Paper sx={{ p: 3, maxWidth: 560 }}>
        <TextField label="Application title" fullWidth value={title}
          onChange={(e) => setTitle(e.target.value)} sx={{ mb: 2 }} />

        {hasLogo && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary">Current logo</Typography>
            <Box>
              <Box component="img" src={`/api/v1/branding/logo?ts=${Date.now()}`} alt="Current logo"
                sx={{ maxHeight: 64, maxWidth: "100%", bgcolor: "grey.100", p: 1, borderRadius: 1 }} />
            </Box>
          </Box>
        )}

        <Button variant="outlined" component="label">
          {file ? `Selected: ${file.name}` : "Choose logo file"}
          <input type="file" hidden accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Button>

        <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
          <Button variant="contained" startIcon={<SaveIcon />} onClick={() => save(false)} disabled={busy}>
            Save
          </Button>
          {hasLogo && (
            <Button color="error" onClick={() => save(true)} disabled={busy}>
              Remove logo
            </Button>
          )}
        </Stack>
      </Paper>
    </Box>
  );
}
