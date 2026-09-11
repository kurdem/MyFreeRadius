import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
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

interface Group {
  id: number;
  name: string;
  description?: string | null;
  client_count: number;
}

export default function ClientGroups() {
  const { isAdmin } = useAuth();
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const load = () =>
    api.get<Group[]>("/client-groups").then((r) => setGroups(r.data)).catch((e) => setError(errorMessage(e)));

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    setError(null);
    try {
      await api.post("/client-groups", { name, description: description || null });
      setOpen(false);
      setName("");
      setDescription("");
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const remove = async (g: Group) => {
    if (!window.confirm(`Delete group "${g.name}"? Clients are not deleted.`)) return;
    try {
      await api.delete(`/client-groups/${g.id}`);
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">Client Groups</Typography>
        {isAdmin && (
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setOpen(true)}>
            Add Group
          </Button>
        )}
      </Stack>
      <Alert severity="info" sx={{ mb: 2 }}>
        Group related RADIUS clients, e.g. a Horizon Connection Server cluster per site.
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
            <TableCell>Description</TableCell>
            <TableCell>Clients</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {groups.map((g) => (
            <TableRow key={g.id} hover>
              <TableCell>{g.name}</TableCell>
              <TableCell>{g.description ?? "-"}</TableCell>
              <TableCell>{g.client_count}</TableCell>
              <TableCell align="right">
                {isAdmin && (
                  <IconButton size="small" color="error" onClick={() => remove(g)}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                )}
              </TableCell>
            </TableRow>
          ))}
          {groups.length === 0 && (
            <TableRow>
              <TableCell colSpan={4}>
                <Typography color="text.secondary" sx={{ py: 2 }}>
                  No groups yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Client Group</DialogTitle>
        <DialogContent>
          <TextField
            label="Name"
            fullWidth
            margin="dense"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <TextField
            label="Description"
            fullWidth
            margin="dense"
            multiline
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={create}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
