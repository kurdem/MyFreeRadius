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
import DeleteIcon from "@mui/icons-material/Delete";
import KeyIcon from "@mui/icons-material/Key";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface UserRow {
  id: number;
  username: string;
  role: "administrator" | "operator" | "auditor";
  is_active: boolean;
}

const ROLES = ["administrator", "operator", "auditor"] as const;

export default function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState({ username: "", password: "", role: "operator" });
  const [pwUser, setPwUser] = useState<UserRow | null>(null);
  const [newPw, setNewPw] = useState("");

  const load = () =>
    api.get<UserRow[]>("/users").then((r) => setUsers(r.data)).catch((e) => setError(errorMessage(e)));

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    setError(null);
    try {
      await api.post("/users", form);
      setAddOpen(false);
      setForm({ username: "", password: "", role: "operator" });
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const patch = async (u: UserRow, body: Record<string, unknown>) => {
    setError(null);
    try {
      await api.put(`/users/${u.id}`, body);
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const remove = async (u: UserRow) => {
    if (!window.confirm(`Delete user "${u.username}"?`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const resetPassword = async () => {
    if (!pwUser) return;
    setError(null);
    try {
      await api.put(`/users/${pwUser.id}`, { password: newPw });
      setPwUser(null);
      setNewPw("");
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">Users</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAddOpen(true)}>
          Add User
        </Button>
      </Stack>
      <Alert severity="info" sx={{ mb: 2 }}>
        Local accounts for the web interface. Administrators manage everything;
        operators can view and run tests; auditors are read-only. The last active
        administrator cannot be removed.
      </Alert>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Username</TableCell>
            <TableCell>Role</TableCell>
            <TableCell>Active</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.id} hover>
              <TableCell>
                {u.username}{" "}
                {me?.id === u.id && <Chip size="small" label="you" sx={{ ml: 0.5 }} />}
              </TableCell>
              <TableCell sx={{ minWidth: 160 }}>
                <Select
                  size="small"
                  value={u.role}
                  onChange={(e) => patch(u, { role: e.target.value })}
                >
                  {ROLES.map((r) => (
                    <MenuItem key={r} value={r}>{r}</MenuItem>
                  ))}
                </Select>
              </TableCell>
              <TableCell>
                <Switch
                  checked={u.is_active}
                  onChange={(e) => patch(u, { is_active: e.target.checked })}
                />
              </TableCell>
              <TableCell align="right">
                <IconButton size="small" title="Reset password" onClick={() => setPwUser(u)}>
                  <KeyIcon fontSize="small" />
                </IconButton>
                <IconButton size="small" color="error" onClick={() => remove(u)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Add User</DialogTitle>
        <DialogContent>
          <TextField label="Username" fullWidth margin="dense" value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <TextField label="Password (min 12)" type="password" fullWidth margin="dense"
            value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <FormControl fullWidth margin="dense">
            <InputLabel>Role</InputLabel>
            <Select label="Role" value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={create}
            disabled={!form.username || form.password.length < 12}>Create</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!pwUser} onClose={() => setPwUser(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Reset password for {pwUser?.username}</DialogTitle>
        <DialogContent>
          <TextField label="New password (min 12)" type="password" fullWidth margin="dense"
            value={newPw} onChange={(e) => setNewPw(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPwUser(null)}>Cancel</Button>
          <Button variant="contained" onClick={resetPassword} disabled={newPw.length < 12}>
            Reset
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
