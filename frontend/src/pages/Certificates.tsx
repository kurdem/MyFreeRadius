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
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface Cert {
  id: number;
  name: string;
  subject: string;
  issuer: string;
  fingerprint_sha256: string;
  not_before: string;
  not_after: string;
  status: "valid" | "expiring" | "expired";
  days_left: number;
}

const statusColor: Record<Cert["status"], "success" | "warning" | "error"> = {
  valid: "success",
  expiring: "warning",
  expired: "error",
};

export default function Certificates() {
  const { isAdmin } = useAuth();
  const [certs, setCerts] = useState<Cert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [pem, setPem] = useState("");

  const load = () =>
    api.get<Cert[]>("/certificates").then((r) => setCerts(r.data)).catch((e) => setError(errorMessage(e)));

  useEffect(() => {
    load();
  }, []);

  const upload = async () => {
    setError(null);
    try {
      await api.post("/certificates", { name, pem });
      setOpen(false);
      setName("");
      setPem("");
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const remove = async (c: Cert) => {
    if (!window.confirm(`Delete certificate "${c.name}"?`)) return;
    try {
      await api.delete(`/certificates/${c.id}`);
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">Certificates</Typography>
        {isAdmin && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>
            Upload CA Certificate
          </Button>
        )}
      </Stack>
      <Alert severity="info" sx={{ mb: 2 }}>
        CA certificates used to validate the LDAPS connection to Active Directory.
        Upload your AD Root/Issuing CA (PEM). They are applied to both the built-in
        connection test and the generated FreeRADIUS LDAP config on the next
        activate. Only public CA certificates are stored — never private keys.
      </Alert>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Name</TableCell>
            <TableCell>Subject</TableCell>
            <TableCell>Issuer</TableCell>
            <TableCell>Expires</TableCell>
            <TableCell>Status</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {certs.map((c) => (
            <TableRow key={c.id} hover>
              <TableCell>{c.name}</TableCell>
              <TableCell><code style={{ fontSize: 12 }}>{c.subject}</code></TableCell>
              <TableCell><code style={{ fontSize: 12 }}>{c.issuer}</code></TableCell>
              <TableCell>
                {new Date(c.not_after).toLocaleDateString()}
                <Typography variant="caption" color="text.secondary" display="block">
                  {c.days_left >= 0 ? `in ${c.days_left} days` : `${-c.days_left} days ago`}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip size="small" label={c.status} color={statusColor[c.status]} />
              </TableCell>
              <TableCell align="right">
                {isAdmin && (
                  <IconButton size="small" color="error" onClick={() => remove(c)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                )}
              </TableCell>
            </TableRow>
          ))}
          {certs.length === 0 && (
            <TableRow>
              <TableCell colSpan={6}>
                <Typography color="text.secondary" sx={{ py: 2 }}>
                  No CA certificates uploaded. LDAPS uses the system trust store until you add one.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Upload CA Certificate</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <TextField label="Name" fullWidth margin="dense" value={name}
            onChange={(e) => setName(e.target.value)} helperText="e.g. Corp Root CA" />
          <TextField
            label="PEM certificate"
            fullWidth
            margin="dense"
            multiline
            minRows={8}
            value={pem}
            onChange={(e) => setPem(e.target.value)}
            placeholder={"-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"}
            slotProps={{ input: { style: { fontFamily: "monospace", fontSize: 12 } } }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={upload} disabled={!name || !pem}>
            Upload
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
