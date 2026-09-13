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
  FormControlLabel,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import PolicyIcon from "@mui/icons-material/Policy";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface ReplyAttr {
  name: string;
  value: string;
}
interface Policy {
  id: number;
  name: string;
  priority: number;
  enabled: boolean;
  client_group_id: number | null;
  client_group_name?: string | null;
  ad_group_dn: string | null;
  ad_group_name: string | null;
  action: "allow" | "deny";
  reply_attributes: ReplyAttr[];
}
interface Group {
  id: number;
  name: string;
}

type Draft = {
  id?: number;
  name: string;
  priority: number;
  enabled: boolean;
  client_group_id: number | null;
  ad_group_dn: string;
  ad_group_name: string;
  action: "allow" | "deny";
  reply_attributes: ReplyAttr[];
};

const empty: Draft = {
  name: "",
  priority: 100,
  enabled: true,
  client_group_id: null,
  ad_group_dn: "",
  ad_group_name: "",
  action: "allow",
  reply_attributes: [],
};

export default function Policies() {
  const { isAdmin } = useAuth();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  const load = () => {
    api.get<Policy[]>("/policies").then((r) => setPolicies(r.data)).catch((e) => setError(errorMessage(e)));
    api.get<Group[]>("/client-groups").then((r) => setGroups(r.data)).catch(() => undefined);
  };

  useEffect(() => {
    load();
  }, []);

  const openNew = () => setDraft({ ...empty });
  const openEdit = (p: Policy) =>
    setDraft({
      id: p.id,
      name: p.name,
      priority: p.priority,
      enabled: p.enabled,
      client_group_id: p.client_group_id,
      ad_group_dn: p.ad_group_dn ?? "",
      ad_group_name: p.ad_group_name ?? "",
      action: p.action,
      reply_attributes: p.reply_attributes ?? [],
    });

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    const payload = {
      name: draft.name,
      priority: draft.priority,
      enabled: draft.enabled,
      client_group_id: draft.client_group_id,
      ad_group_dn: draft.ad_group_dn.trim() || null,
      ad_group_name: draft.ad_group_name.trim() || null,
      action: draft.action,
      reply_attributes: draft.reply_attributes.filter((a) => a.name.trim()),
    };
    try {
      if (draft.id) await api.put(`/policies/${draft.id}`, payload);
      else await api.post("/policies", payload);
      setDraft(null);
      load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (p: Policy) => {
    if (!window.confirm(`Delete policy "${p.name}"?`)) return;
    setBusy(true);
    try {
      await api.delete(`/policies/${p.id}`);
      load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const setAttr = (i: number, key: keyof ReplyAttr, val: string) => {
    if (!draft) return;
    const next = draft.reply_attributes.slice();
    next[i] = { ...next[i], [key]: val };
    setDraft({ ...draft, reply_attributes: next });
  };

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
        <PolicyIcon />
        <Typography variant="h4" sx={{ flexGrow: 1 }}>
          Authentication Policies
        </Typography>
        {isAdmin && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={openNew} disabled={busy}>
            New policy
          </Button>
        )}
      </Stack>

      <Alert severity="info" sx={{ mb: 2 }}>
        Ordered rules mapping a request's <b>RADIUS client group</b> and the user's{" "}
        <b>AD group</b> to an <b>allow / deny</b> decision plus optional RADIUS reply
        attributes. Rules are evaluated top to bottom by priority — the first match
        wins. Empty client group or AD group means "any". With no policies defined,
        authentication is unaffected; once policies exist, a request that matches no
        rule is denied. Enforced by the backend, so it applies with or without MFA.
      </Alert>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Priority</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Client group</TableCell>
              <TableCell>AD group</TableCell>
              <TableCell>Action</TableCell>
              <TableCell>Reply</TableCell>
              <TableCell>Enabled</TableCell>
              {isAdmin && <TableCell align="right">Actions</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {policies.map((p) => (
              <TableRow key={p.id} hover>
                <TableCell>{p.priority}</TableCell>
                <TableCell>{p.name}</TableCell>
                <TableCell>{p.client_group_name ?? <em>any</em>}</TableCell>
                <TableCell>{p.ad_group_name || p.ad_group_dn || <em>any</em>}</TableCell>
                <TableCell>
                  <Chip size="small" label={p.action} color={p.action === "allow" ? "success" : "error"} />
                </TableCell>
                <TableCell>{p.reply_attributes.length || "-"}</TableCell>
                <TableCell>
                  <Chip size="small" label={p.enabled ? "on" : "off"} color={p.enabled ? "default" : "warning"} />
                </TableCell>
                {isAdmin && (
                  <TableCell align="right">
                    <Tooltip title="Edit">
                      <IconButton size="small" onClick={() => openEdit(p)} disabled={busy}>
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton size="small" color="error" onClick={() => remove(p)} disabled={busy}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                )}
              </TableRow>
            ))}
            {policies.length === 0 && (
              <TableRow>
                <TableCell colSpan={isAdmin ? 8 : 7}>
                  <Typography color="text.secondary" sx={{ py: 2 }}>
                    No policies yet. Authentication is unrestricted by policies.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={!!draft} onClose={() => setDraft(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{draft?.id ? "Edit policy" : "New policy"}</DialogTitle>
        <DialogContent dividers>
          {draft && (
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              <TextField label="Name" value={draft.name} required
                onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              <Stack direction="row" spacing={2}>
                <TextField label="Priority" type="number" value={draft.priority} sx={{ width: 140 }}
                  helperText="Lower first"
                  onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) })} />
                <TextField select label="Action" value={draft.action} fullWidth
                  onChange={(e) => setDraft({ ...draft, action: e.target.value as "allow" | "deny" })}>
                  <MenuItem value="allow">Allow</MenuItem>
                  <MenuItem value="deny">Deny</MenuItem>
                </TextField>
              </Stack>
              <TextField select label="Client group" value={draft.client_group_id ?? ""}
                onChange={(e) =>
                  setDraft({ ...draft, client_group_id: e.target.value === "" ? null : Number(e.target.value) })}>
                <MenuItem value="">Any client group</MenuItem>
                {groups.map((g) => (
                  <MenuItem key={g.id} value={g.id}>{g.name}</MenuItem>
                ))}
              </TextField>
              <TextField label="AD group DN" value={draft.ad_group_dn}
                placeholder="CN=VPN-Users,OU=Groups,DC=corp,DC=local"
                helperText="Leave empty to match any AD group"
                onChange={(e) => setDraft({ ...draft, ad_group_dn: e.target.value })} />
              <TextField label="AD group label (optional)" value={draft.ad_group_name}
                onChange={(e) => setDraft({ ...draft, ad_group_name: e.target.value })} />

              <Box>
                <Stack direction="row" alignItems="center" justifyContent="space-between">
                  <Typography variant="subtitle2">Reply attributes (on allow)</Typography>
                  <Button size="small" startIcon={<AddIcon />}
                    onClick={() => setDraft({ ...draft, reply_attributes: [...draft.reply_attributes, { name: "", value: "" }] })}>
                    Add
                  </Button>
                </Stack>
                {draft.reply_attributes.map((a, i) => (
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }} key={i}>
                    <TextField label="Attribute" size="small" value={a.name} sx={{ flex: 1 }}
                      placeholder="Filter-Id" onChange={(e) => setAttr(i, "name", e.target.value)} />
                    <TextField label="Value" size="small" value={a.value} sx={{ flex: 1 }}
                      onChange={(e) => setAttr(i, "value", e.target.value)} />
                    <IconButton size="small" color="error"
                      onClick={() => setDraft({ ...draft, reply_attributes: draft.reply_attributes.filter((_, j) => j !== i) })}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                ))}
              </Box>

              <FormControlLabel
                control={<Switch checked={draft.enabled}
                  onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />}
                label="Enabled"
              />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDraft(null)}>Cancel</Button>
          <Button variant="contained" onClick={save} disabled={busy || !draft?.name.trim()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
