import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import SaveIcon from "@mui/icons-material/Save";
import QRCode from "qrcode";
import { api, errorMessage } from "../api/client";
import { copyToClipboard } from "../utils/clipboard";
import { useAuth } from "../auth/AuthContext";

interface Token {
  username: string;
  confirmed: boolean;
  created_at: string;
}

export default function Mfa() {
  const { isAdmin } = useAuth();
  const [enabled, setEnabled] = useState(false);
  const [mode, setMode] = useState("totp_only");
  const [tokens, setTokens] = useState<Token[]>([]);
  const [msg, setMsg] = useState<{ s: "success" | "error" | "info"; t: string } | null>(null);

  // Enrollment state
  const [enrollUser, setEnrollUser] = useState("");
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const [code, setCode] = useState("");

  // Self-service enrollment link
  const [linkUser, setLinkUser] = useState("");
  const [link, setLink] = useState<{ url: string; expires: string } | null>(null);

  const loadTokens = () =>
    api.get<Token[]>("/mfa/tokens").then((r) => setTokens(r.data)).catch(() => undefined);

  useEffect(() => {
    api
      .get<{ mfa_enabled: boolean; mfa_mode: string }>("/mfa/settings")
      .then((r) => {
        setEnabled(r.data.mfa_enabled);
        setMode(r.data.mfa_mode);
      })
      .catch((e) => setMsg({ s: "error", t: errorMessage(e) }));
    loadTokens();
  }, []);

  const saveSettings = async () => {
    setMsg(null);
    try {
      await api.put("/mfa/settings", { mfa_enabled: enabled, mfa_mode: mode });
      setMsg({ s: "success", t: "MFA settings saved. Remember to Generate + Activate the configuration." });
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    }
  };

  const enroll = async () => {
    setMsg(null);
    setQr(null);
    setSecret(null);
    try {
      const r = await api.post<{ username: string; secret: string; otpauth_uri: string }>(
        "/mfa/enroll",
        { username: enrollUser },
      );
      const dataUrl = await QRCode.toDataURL(r.data.otpauth_uri, { margin: 1, width: 220 });
      setQr(dataUrl);
      setSecret(r.data.secret);
      setPendingUser(r.data.username);
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    }
  };

  const confirm = async () => {
    if (!pendingUser) return;
    setMsg(null);
    try {
      await api.post("/mfa/confirm", { username: pendingUser, code });
      setMsg({ s: "success", t: `MFA activated for ${pendingUser}.` });
      setQr(null);
      setSecret(null);
      setPendingUser(null);
      setCode("");
      setEnrollUser("");
      loadTokens();
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    }
  };

  const createLink = async () => {
    setMsg(null);
    setLink(null);
    try {
      const r = await api.post<{ enroll_path: string; expires_at: string }>(
        "/mfa/enroll-link", { username: linkUser });
      setLink({ url: window.location.origin + r.data.enroll_path, expires: r.data.expires_at });
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    }
  };

  const remove = async (t: Token) => {
    if (!window.confirm(`Remove MFA token for "${t.username}"?`)) return;
    try {
      await api.delete(`/mfa/tokens/${encodeURIComponent(t.username)}`);
      loadTokens();
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    }
  };

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">Multi-Factor Authentication</Typography>
        <Chip label={enabled ? "Enabled" : "Disabled"} color={enabled ? "success" : "default"} />
      </Stack>

      <Alert severity="info" sx={{ mb: 2 }}>
        TOTP second factor. When enabled and activated, FreeRADIUS delegates
        authentication to this appliance, which verifies the one-time code. In
        <b> totp_only</b> mode the RADIUS passcode is the 6-digit OTP (Horizon
        validates the Windows password itself). In <b>ad_password_plus_totp</b>
        mode the passcode is the AD password followed by the 6-digit OTP.
      </Alert>

      {msg && (
        <Alert severity={msg.s} sx={{ mb: 2, whiteSpace: "pre-wrap" }} onClose={() => setMsg(null)}>
          {msg.t}
        </Alert>
      )}

      <Paper sx={{ p: 3, mb: 3, maxWidth: 680 }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Settings</Typography>
        <FormControlLabel
          control={<Switch checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />}
          label="Enable MFA"
        />
        <FormControl fullWidth margin="dense" sx={{ maxWidth: 360 }}>
          <InputLabel>Mode</InputLabel>
          <Select label="Mode" value={mode} onChange={(e) => setMode(e.target.value)}>
            <MenuItem value="totp_only">totp_only (passcode = OTP)</MenuItem>
            <MenuItem value="ad_password_plus_totp">ad_password_plus_totp (AD password + OTP)</MenuItem>
          </Select>
        </FormControl>
        {isAdmin && (
          <Box sx={{ mt: 2 }}>
            <Button variant="contained" startIcon={<SaveIcon />} onClick={saveSettings}>
              Save
            </Button>
          </Box>
        )}
      </Paper>

      {isAdmin && (
        <Paper sx={{ p: 3, mb: 3, maxWidth: 680 }}>
          <Typography variant="h6" sx={{ mb: 2 }}>Enroll a user</Typography>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={8}>
              <TextField
                label="AD username (sAMAccountName)"
                fullWidth
                value={enrollUser}
                onChange={(e) => setEnrollUser(e.target.value)}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <Button variant="outlined" onClick={enroll} disabled={!enrollUser}>
                Generate token
              </Button>
            </Grid>
          </Grid>

          {qr && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Scan with an authenticator app (e.g. Microsoft Authenticator), then enter a code to confirm.
              </Typography>
              <img src={qr} alt="TOTP QR code" style={{ display: "block" }} />
              {secret && (
                <Typography variant="caption" color="text.secondary">
                  Manual key: <code>{secret}</code>
                </Typography>
              )}
              <Stack direction="row" spacing={2} sx={{ mt: 2 }} alignItems="center">
                <TextField
                  label="6-digit code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  sx={{ width: 160 }}
                />
                <Button variant="contained" onClick={confirm} disabled={code.length < 6}>
                  Confirm
                </Button>
              </Stack>
            </Box>
          )}
        </Paper>
      )}

      {isAdmin && (
        <Paper sx={{ p: 3, mb: 3, maxWidth: 680 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>Self-service enrollment link</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Generate a one-time, 24-hour link and send it to the user (e.g. by email).
            They open it without logging in, scan the QR code and confirm — no admin
            interaction needed.
          </Typography>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={8}>
              <TextField label="AD username (sAMAccountName)" fullWidth value={linkUser}
                onChange={(e) => setLinkUser(e.target.value)} />
            </Grid>
            <Grid item xs={12} sm={4}>
              <Button variant="outlined" onClick={createLink} disabled={!linkUser}>
                Generate link
              </Button>
            </Grid>
          </Grid>
          {link && (
            <Box sx={{ mt: 2 }}>
              <TextField label="Enrollment link" fullWidth value={link.url}
                InputProps={{ readOnly: true }} onFocus={(e) => e.target.select()} />
              <Stack direction="row" spacing={1} sx={{ mt: 1 }} alignItems="center">
                <Button size="small" onClick={async () => {
                  const ok = await copyToClipboard(link.url);
                  setMsg(ok
                    ? { s: "success", t: "Link copied to clipboard." }
                    : { s: "info", t: "Could not copy automatically — select the link field and copy manually." });
                }}>
                  Copy link
                </Button>
                <Typography variant="caption" color="text.secondary">
                  Expires {new Date(link.expires).toLocaleString()} · single use
                </Typography>
              </Stack>
            </Box>
          )}
        </Paper>
      )}

      <Typography variant="h6" sx={{ mb: 1 }}>Enrolled tokens</Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Username</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Created</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {tokens.map((t) => (
            <TableRow key={t.username} hover>
              <TableCell>{t.username}</TableCell>
              <TableCell>
                <Chip size="small" label={t.confirmed ? "Confirmed" : "Pending"}
                      color={t.confirmed ? "success" : "warning"} />
              </TableCell>
              <TableCell>{new Date(t.created_at).toLocaleString()}</TableCell>
              <TableCell align="right">
                {isAdmin && (
                  <IconButton size="small" color="error" onClick={() => remove(t)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                )}
              </TableCell>
            </TableRow>
          ))}
          {tokens.length === 0 && (
            <TableRow>
              <TableCell colSpan={4}>
                <Typography color="text.secondary" sx={{ py: 2 }}>
                  No tokens enrolled yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Box>
  );
}
