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
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ScienceIcon from "@mui/icons-material/Science";
import SaveIcon from "@mui/icons-material/Save";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface ADConfig {
  domain: string;
  primary_dc: string;
  secondary_dc?: string | null;
  port: number;
  use_ldaps: boolean;
  verify_tls: boolean;
  base_dn: string;
  bind_user: string;
  timeout_seconds: number;
  enabled: boolean;
  has_bind_password?: boolean;
}

interface ADGroup {
  id: number;
  name: string;
  group_dn: string;
  access: "allow" | "deny";
  attribute?: string | null;
}

const emptyConfig: ADConfig & { bind_password: string } = {
  domain: "",
  primary_dc: "",
  secondary_dc: "",
  port: 636,
  use_ldaps: true,
  verify_tls: true,
  base_dn: "",
  bind_user: "",
  timeout_seconds: 5,
  enabled: false,
  bind_password: "",
};

export default function ActiveDirectory() {
  const { isAdmin } = useAuth();
  const [form, setForm] = useState({ ...emptyConfig });
  const [configured, setConfigured] = useState(false);
  const [groups, setGroups] = useState<ADGroup[]>([]);
  const [msg, setMsg] = useState<{ s: "success" | "error" | "info"; t: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);
  const [newGroup, setNewGroup] = useState({ name: "", group_dn: "", access: "allow", attribute: "" });

  const loadGroups = () =>
    api.get<ADGroup[]>("/active-directory/groups").then((r) => setGroups(r.data)).catch(() => undefined);

  useEffect(() => {
    api
      .get<ADConfig | null>("/active-directory")
      .then((r) => {
        if (r.data) {
          setForm({ ...emptyConfig, ...r.data, secondary_dc: r.data.secondary_dc ?? "", bind_password: "" });
          setConfigured(true);
        }
      })
      .catch((e) => setMsg({ s: "error", t: errorMessage(e) }));
    loadGroups();
  }, []);

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const payload: Record<string, unknown> = {
        domain: form.domain,
        primary_dc: form.primary_dc,
        secondary_dc: form.secondary_dc || null,
        port: Number(form.port),
        use_ldaps: form.use_ldaps,
        verify_tls: form.verify_tls,
        base_dn: form.base_dn,
        bind_user: form.bind_user,
        timeout_seconds: Number(form.timeout_seconds),
        enabled: form.enabled,
      };
      if (form.bind_password) payload.bind_password = form.bind_password;
      await api.put("/active-directory", payload);
      setConfigured(true);
      setForm({ ...form, bind_password: "" });
      setMsg({ s: "success", t: "Active Directory configuration saved." });
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const testConnection = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.post<{ success: boolean; message: string; details?: string }>(
        "/active-directory/test",
      );
      setMsg({
        s: r.data.success ? "success" : "error",
        t: (r.data.message || "") + (r.data.details ? `\n${r.data.details}` : ""),
      });
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const addGroup = async () => {
    try {
      await api.post("/active-directory/groups", {
        name: newGroup.name,
        group_dn: newGroup.group_dn,
        access: newGroup.access,
        attribute: newGroup.attribute || null,
      });
      setGroupOpen(false);
      setNewGroup({ name: "", group_dn: "", access: "allow", attribute: "" });
      loadGroups();
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    }
  };

  const deleteGroup = async (g: ADGroup) => {
    if (!window.confirm(`Delete group "${g.name}"?`)) return;
    try {
      await api.delete(`/active-directory/groups/${g.id}`);
      loadGroups();
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    }
  };

  const set = (k: keyof typeof form, v: unknown) => setForm({ ...form, [k]: v });

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">Active Directory</Typography>
        <Chip
          label={configured ? (form.enabled ? "Configured" : "Configured (disabled)") : "Not configured"}
          color={configured && form.enabled ? "success" : "default"}
        />
      </Stack>

      <Alert severity="info" sx={{ mb: 2 }}>
        Configure and <b>test</b> the LDAP/LDAPS connection, then add the allowed AD
        group(s). When <b>Enabled</b> and after you activate on the Configuration page,
        FreeRADIUS authenticates RADIUS logins against AD (PAP bind) with group
        authorization. Horizon must be set to <b>PAP</b> for now.
      </Alert>

      {form.use_ldaps && !form.verify_tls && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          ⚠ LDAPS is configured without certificate validation. Do not use this in production.
        </Alert>
      )}

      {msg && (
        <Alert severity={msg.s} sx={{ mb: 2, whiteSpace: "pre-wrap" }} onClose={() => setMsg(null)}>
          {msg.t}
        </Alert>
      )}

      <Paper sx={{ p: 3, mb: 3, maxWidth: 820 }}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <TextField label="Domain" fullWidth value={form.domain}
              onChange={(e) => set("domain", e.target.value)} helperText="e.g. corp.example.local" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField label="Base DN" fullWidth value={form.base_dn}
              onChange={(e) => set("base_dn", e.target.value)} helperText="e.g. DC=corp,DC=example,DC=local" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField label="Primary Domain Controller" fullWidth value={form.primary_dc}
              onChange={(e) => set("primary_dc", e.target.value)} helperText="dc01.corp.example.local" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField label="Secondary DC (optional)" fullWidth value={form.secondary_dc ?? ""}
              onChange={(e) => set("secondary_dc", e.target.value)} />
          </Grid>
          <Grid item xs={6} sm={3}>
            <TextField label="Port" type="number" fullWidth value={form.port}
              onChange={(e) => set("port", e.target.value)} helperText="389 or 636" />
          </Grid>
          <Grid item xs={6} sm={3}>
            <TextField label="Timeout (s)" type="number" fullWidth value={form.timeout_seconds}
              onChange={(e) => set("timeout_seconds", e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField label="Bind User" fullWidth value={form.bind_user}
              onChange={(e) => set("bind_user", e.target.value)}
              helperText="UPN (svc-radius@corp.example.local) or DN" />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              label={configured ? "Bind Password (blank = keep)" : "Bind Password"}
              type="password" fullWidth value={form.bind_password}
              onChange={(e) => set("bind_password", e.target.value)} />
          </Grid>
          <Grid item xs={12}>
            <FormControlLabel control={<Switch checked={form.use_ldaps}
              onChange={(e) => set("use_ldaps", e.target.checked)} />} label="Use LDAPS (TLS)" />
            <FormControlLabel control={<Switch checked={form.verify_tls}
              onChange={(e) => set("verify_tls", e.target.checked)} />} label="Verify TLS certificate" />
            <FormControlLabel control={<Switch checked={form.enabled}
              onChange={(e) => set("enabled", e.target.checked)} />} label="Enabled" />
          </Grid>
        </Grid>

        {isAdmin && (
          <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
            <Button variant="contained" startIcon={<SaveIcon />} onClick={save} disabled={busy}>
              Save
            </Button>
            <Button startIcon={<ScienceIcon />} onClick={testConnection} disabled={busy || !configured}>
              Test Connection
            </Button>
          </Stack>
        )}
      </Paper>

      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h6">Allowed AD Groups</Typography>
        {isAdmin && (
          <Button startIcon={<AddIcon />} onClick={() => setGroupOpen(true)}>
            Add Group
          </Button>
        )}
      </Stack>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Name</TableCell>
            <TableCell>Group DN</TableCell>
            <TableCell>Access</TableCell>
            <TableCell>Attribute</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {groups.map((g) => (
            <TableRow key={g.id} hover>
              <TableCell>{g.name}</TableCell>
              <TableCell><code style={{ fontSize: 12 }}>{g.group_dn}</code></TableCell>
              <TableCell>
                <Chip size="small" label={g.access} color={g.access === "allow" ? "success" : "error"} />
              </TableCell>
              <TableCell>{g.attribute ?? "-"}</TableCell>
              <TableCell align="right">
                {isAdmin && (
                  <IconButton size="small" color="error" onClick={() => deleteGroup(g)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                )}
              </TableCell>
            </TableRow>
          ))}
          {groups.length === 0 && (
            <TableRow>
              <TableCell colSpan={5}>
                <Typography color="text.secondary" sx={{ py: 2 }}>
                  No groups defined. Add the AD groups allowed to authenticate.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={groupOpen} onClose={() => setGroupOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add AD Group</DialogTitle>
        <DialogContent>
          <TextField label="Name" fullWidth margin="dense" value={newGroup.name}
            onChange={(e) => setNewGroup({ ...newGroup, name: e.target.value })}
            helperText="Friendly label, e.g. Horizon-Users" />
          <TextField label="Group DN" fullWidth margin="dense" value={newGroup.group_dn}
            onChange={(e) => setNewGroup({ ...newGroup, group_dn: e.target.value })}
            helperText="CN=Horizon-Users,OU=Groups,DC=corp,DC=example,DC=local" />
          <FormControl fullWidth margin="dense">
            <InputLabel>Access</InputLabel>
            <Select label="Access" value={newGroup.access}
              onChange={(e) => setNewGroup({ ...newGroup, access: e.target.value })}>
              <MenuItem value="allow">Allow</MenuItem>
              <MenuItem value="deny">Deny</MenuItem>
            </Select>
          </FormControl>
          <TextField label="Attribute (optional)" fullWidth margin="dense" value={newGroup.attribute}
            onChange={(e) => setNewGroup({ ...newGroup, attribute: e.target.value })}
            helperText="e.g. Admin / User (used when policies are wired)" />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGroupOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={addGroup}>Save</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
