import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import QRCode from "qrcode";
import { api, errorMessage } from "../api/client";

/** Public, no-login MFA self-enrollment page reached via a one-time link. */
export default function Enroll() {
  const { token } = useParams<{ token: string }>();
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<{ username: string; otpauth_uri: string; secret: string }>(`/mfa/enroll/${token}`)
      .then(async (r) => {
        setUsername(r.data.username);
        setSecret(r.data.secret);
        setQr(await QRCode.toDataURL(r.data.otpauth_uri, { margin: 1, width: 220 }));
      })
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [token]);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/mfa/enroll/${token}/confirm`, { code });
      setDone(true);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center",
               justifyContent: "center", bgcolor: "grey.100", p: 2 }}>
      <Card sx={{ width: 420, boxShadow: 4 }}>
        <CardContent>
          <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
            Set up your authenticator
          </Typography>

          {loading && <CircularProgress />}

          {!loading && error && !qr && (
            <Alert severity="error">{error}</Alert>
          )}

          {done ? (
            <Alert severity="success">
              MFA is set up for <b>{username}</b>. You can close this page.
            </Alert>
          ) : (
            qr && (
              <>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Account: <b>{username}</b>. Scan this code with an authenticator app
                  (Microsoft Authenticator, Google Authenticator, …), then enter a
                  6-digit code to finish.
                </Typography>
                <Box sx={{ textAlign: "center", mb: 1 }}>
                  <img src={qr} alt="TOTP QR code" />
                </Box>
                <Typography variant="caption" color="text.secondary">
                  Manual key: <code>{secret}</code>
                </Typography>
                {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
                <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
                  <TextField label="6-digit code" value={code}
                    onChange={(e) => setCode(e.target.value)} sx={{ width: 160 }} />
                  <Button variant="contained" onClick={confirm}
                    disabled={busy || code.length < 6}>Confirm</Button>
                </Stack>
              </>
            )
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
