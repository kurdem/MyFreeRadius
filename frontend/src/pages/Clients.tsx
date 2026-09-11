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
  IconButton,
  InputLabel,
  MenuItem,
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
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface Client {
  id: number;
  name: string;
  ipaddr: string;
  nas_type: string;
  description?: string | null;
  location?: string | null;
  tags?: string | null;
  enabled: boolean;
  require_message_authenticator: boolean;
  group_id?: number | null;
  has_secret: boolean;
}

interface Group {
  id: number;
  name: string;
}

const NAS_TYPES = ["vmware", "other", "cisco", "juniper", "mikrotik", "aruba"];

const empty = {
  name: "",
  ipaddr: "",
  shared_secret: "",
  nas_type: "vmware",
  description: "",
  location: "",
  tags: "",
  enabled: true,
  require_message_authenticator: true,
  group_id: "" as string | number,
};

export default function Clients() {
  const { isAdmin } = useAuth();
  const [clients, setClients] = useState<Client[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Client | null>(null);
  const [form, setForm] = useState({ ...empty });

  const load = () => {
    api.get<Client[]>("/clients").then((r) => setClients(r.data)).catch((e) => setError(errorMessage(e)));
    api.get<Group[]>("/client-groups").then((r) => setGroups(r.data)).catch(() => undefined);
  };

  useEffect(load, []);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...empty });
    setError(null);
    setOpen(true);
  };

  const openEdit = (c: Client) => {
    setEditing(c);
    setForm({
      name: c.name,
      ipaddr: c.ipaddr,
      shared_secret: "",
      nas_type: c.nas_type,
      description: c.description ?? "",
      location: c.location ?? "",
      tags: c.tags ?? "",
      enabled: c.enabled,
      require_message_authenticator: c.require_message_authenticator ?? true,
      group_id: c.group_id ?? "",
    });
    setError(null);
    setOpen(true);
  };

  const save = async () => {
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        name: form.name,
        ipaddr: form.ipaddr,
        nas_type: form.nas_type,
        description: form.description || null,
        location: form.location || null,
        tags: form.tags || null,
        enabled: form.enabled,
        require_message_authenticator: form.require_message_authenticator,
        group_id: form.group_id === "" ? null : Number(form.group_id),
      };
      if (form.shared_secret) payload.shared_secret = form.shared_secret;

      if (editing) {
        await api.put(`/clients/${editing.id}`, payload);
      } else {
        await api.post("/clients", payload);
      }
      setOpen(false);
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const remove = async (c: Client) => {
    if (!window.confirm(`Delete RADIUS client "${c.name}"?`)) return;
    try {
      await api.delete(`/clients/${c.id}`);
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">RADIUS Clients</Typography>
        {isAdmin && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
            Add Client
          </Button>
        )}
      </Stack>

      <Alert severity="info" sx={{ mb: 2 }}>
        Add each Horizon Connection Server as a RADIUS client. Changes take effect
        after you generate &amp; activate the configuration on the Configuration page.
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
            <TableCell>IP / Network</TableCell>
            <TableCell>NAS Type</TableCell>
            <TableCell>Location</TableCell>
            <TableCell>Status</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {clients.map((c) => (
            <TableRow key={c.id} hover>
              <TableCell>{c.name}</TableCell>
              <TableCell><code>{c.ipaddr}</code></TableCell>
              <TableCell>{c.nas_type}</TableCell>
              <TableCell>{c.location ?? "-"}</TableCell>
              <TableCell>
                <Chip
                  size="small"
                  label={c.enabled ? "Enabled" : "Disabled"}
                  color={c.enabled ? "success" : "default"}
                />
              </TableCell>
              <TableCell align="right">
                {isAdmin && (
                  <>
                    <IconButton size="small" onClick={() => openEdit(c)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton size="small" color="error" onClick={() => remove(c)}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </>
                )}
              </TableCell>
            </TableRow>
          ))}
          {clients.length === 0 && (
            <TableRow>
              <TableCell colSpan={6}>
                <Typography color="text.secondary" sx={{ py: 2 }}>
                  No RADIUS clients yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editing ? `Edit ${editing.name}` : "Add RADIUS Client"}</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <TextField
            label="Name"
            fullWidth
            margin="dense"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            helperText="Letters, digits, dot, dash, underscore. e.g. Horizon-CS01"
          />
          <TextField
            label="IP address or CIDR"
            fullWidth
            margin="dense"
            value={form.ipaddr}
            onChange={(e) => setForm({ ...form, ipaddr: e.target.value })}
            helperText="e.g. 10.10.20.11 or 10.10.20.0/24"
          />
          <TextField
            label={editing ? "Shared secret (leave blank to keep)" : "Shared secret"}
            type="password"
            fullWidth
            margin="dense"
            value={form.shared_secret}
            onChange={(e) => setForm({ ...form, shared_secret: e.target.value })}
            helperText="8-128 chars, no quotes/backslashes/spaces"
          />
          <FormControl fullWidth margin="dense">
            <InputLabel>NAS Type</InputLabel>
            <Select
              label="NAS Type"
              value={form.nas_type}
              onChange={(e) => setForm({ ...form, nas_type: e.target.value })}
            >
              {NAS_TYPES.map((t) => (
                <MenuItem key={t} value={t}>
                  {t === "vmware" ? "vmware (VMware Horizon)" : t}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth margin="dense">
            <InputLabel>Group</InputLabel>
            <Select
              label="Group"
              value={form.group_id}
              onChange={(e) => setForm({ ...form, group_id: e.target.value })}
            >
              <MenuItem value="">
                <em>None</em>
              </MenuItem>
              {groups.map((g) => (
                <MenuItem key={g.id} value={g.id}>
                  {g.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label="Location"
            fullWidth
            margin="dense"
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
          />
          <TextField
            label="Tags (comma-separated)"
            fullWidth
            margin="dense"
            value={form.tags}
            onChange={(e) => setForm({ ...form, tags: e.target.value })}
          />
          <TextField
            label="Description"
            fullWidth
            multiline
            rows={2}
            margin="dense"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              />
            }
            label="Enabled"
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.require_message_authenticator}
                onChange={(e) =>
                  setForm({ ...form, require_message_authenticator: e.target.checked })
                }
              />
            }
            label="Require Message-Authenticator (BlastRADIUS mitigation)"
          />
          <Typography variant="caption" color="text.secondary" display="block">
            Recommended for VMware Horizon / UAG, which send a Message-Authenticator.
            Leave off for clients that do not send one.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={save}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
