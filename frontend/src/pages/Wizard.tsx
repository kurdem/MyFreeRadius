import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControlLabel,
  Grid,
  Paper,
  Step,
  StepContent,
  StepLabel,
  Stepper,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { api, errorMessage } from "../api/client";

type Msg = { s: "success" | "error" | "info"; t: string } | null;

export default function Wizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);

  // Step data
  const [pw, setPw] = useState({ current: "", next: "" });
  const [ad, setAd] = useState({
    domain: "", primary_dc: "", secondary_dc: "", port: 636, use_ldaps: true,
    verify_tls: true, base_dn: "", bind_user: "", bind_password: "", enabled: true,
    timeout_seconds: 5,
  });
  const [client, setClient] = useState({ name: "", ipaddr: "", shared_secret: "" });
  const [group, setGroup] = useState({ name: "", group_dn: "" });
  const [test, setTest] = useState({ username: "", password: "" });

  const next = () => { setMsg(null); setStep((s) => s + 1); };
  const back = () => { setMsg(null); setStep((s) => Math.max(0, s - 1)); };

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setMsg({ s: "error", t: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };

  const changePassword = () =>
    run(async () => {
      await api.post("/auth/change-password",
        { current_password: pw.current, new_password: pw.next });
      setMsg({ s: "success", t: "Password changed." });
      next();
    });

  const saveAd = () =>
    run(async () => {
      await api.put("/active-directory", {
        ...ad, secondary_dc: ad.secondary_dc || null,
        port: Number(ad.port), timeout_seconds: Number(ad.timeout_seconds),
      });
      setMsg({ s: "success", t: "Active Directory saved. You can test the connection." });
    });

  const testAd = () =>
    run(async () => {
      const r = await api.post<{ success: boolean; message: string; details?: string }>(
        "/active-directory/test");
      setMsg({
        s: r.data.success ? "success" : "error",
        t: (r.data.message || "") + (r.data.details ? `\n${r.data.details}` : ""),
      });
    });

  const addClient = () =>
    run(async () => {
      await api.post("/clients", { ...client, nas_type: "vmware" });
      setMsg({ s: "success", t: `Client ${client.name} added.` });
      next();
    });

  const addGroup = () =>
    run(async () => {
      await api.post("/active-directory/groups", { name: group.name, group_dn: group.group_dn });
      setMsg({ s: "success", t: `Group ${group.name} added.` });
      next();
    });

  const activate = () =>
    run(async () => {
      const pending = await api.get<{ id: number } | null>("/configuration/pending");
      if (!pending.data) { setMsg({ s: "info", t: "No changes to activate." }); return; }
      const v = await api.post<{ valid: boolean; details?: string }>(
        `/configuration/${pending.data.id}/validate`);
      if (!v.data.valid) {
        setMsg({ s: "error", t: `Validation failed: ${v.data.details ?? ""}` });
        return;
      }
      const a = await api.post<{ success: boolean; message: string; details?: string }>(
        `/configuration/${pending.data.id}/activate`);
      setMsg({
        s: a.data.success ? "success" : "error",
        t: a.data.success ? "Configuration activated." : (a.data.details ?? a.data.message),
      });
    });

  const runTest = () =>
    run(async () => {
      const r = await api.post<{ result: string; accepted: boolean; duration_ms: number }>(
        "/radius/test", test);
      setMsg({
        s: r.data.accepted ? "success" : "error",
        t: `${r.data.result} (${r.data.duration_ms} ms)`,
      });
    });

  const finish = () =>
    run(async () => {
      await api.post("/setup/complete");
      navigate("/");
    });

  return (
    <Box sx={{ maxWidth: 760 }}>
      <Typography variant="h4" sx={{ mb: 1 }}>Setup Wizard</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Get FreeRADIUS ready for VMware Horizon &amp; Active Directory. Each step
        can be skipped if you've already done it elsewhere.
      </Typography>

      {msg && (
        <Alert severity={msg.s} sx={{ mb: 2, whiteSpace: "pre-wrap" }} onClose={() => setMsg(null)}>
          {msg.t}
        </Alert>
      )}

      <Paper sx={{ p: 2 }}>
        <Stepper activeStep={step} orientation="vertical">
          {/* 1. Administrator */}
          <Step>
            <StepLabel>Create / secure the administrator</StepLabel>
            <StepContent>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Change the initial bootstrap password.
              </Typography>
              <TextField label="Current password" type="password" fullWidth margin="dense"
                value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
              <TextField label="New password (min 12 chars)" type="password" fullWidth margin="dense"
                value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
              <Box sx={{ mt: 1 }}>
                <Button variant="contained" onClick={changePassword}
                  disabled={busy || !pw.current || pw.next.length < 12}>Change &amp; continue</Button>
                <Button onClick={next} sx={{ ml: 1 }}>Skip</Button>
              </Box>
            </StepContent>
          </Step>

          {/* 2. Active Directory */}
          <Step>
            <StepLabel>Configure Active Directory</StepLabel>
            <StepContent>
              <Grid container spacing={1}>
                <Grid item xs={12} sm={6}>
                  <TextField label="Domain" fullWidth margin="dense" value={ad.domain}
                    onChange={(e) => setAd({ ...ad, domain: e.target.value })} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField label="Base DN" fullWidth margin="dense" value={ad.base_dn}
                    onChange={(e) => setAd({ ...ad, base_dn: e.target.value })} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField label="Primary DC" fullWidth margin="dense" value={ad.primary_dc}
                    onChange={(e) => setAd({ ...ad, primary_dc: e.target.value })} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField label="Port" type="number" fullWidth margin="dense" value={ad.port}
                    onChange={(e) => setAd({ ...ad, port: Number(e.target.value) })} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField label="Bind user" fullWidth margin="dense" value={ad.bind_user}
                    onChange={(e) => setAd({ ...ad, bind_user: e.target.value })} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField label="Bind password" type="password" fullWidth margin="dense"
                    value={ad.bind_password}
                    onChange={(e) => setAd({ ...ad, bind_password: e.target.value })} />
                </Grid>
              </Grid>
              <FormControlLabel control={<Switch checked={ad.use_ldaps}
                onChange={(e) => setAd({ ...ad, use_ldaps: e.target.checked })} />} label="LDAPS" />
              <FormControlLabel control={<Switch checked={ad.verify_tls}
                onChange={(e) => setAd({ ...ad, verify_tls: e.target.checked })} />} label="Verify TLS" />
              <Box sx={{ mt: 1 }}>
                <Button variant="outlined" onClick={saveAd} disabled={busy}>Save</Button>
                <Button onClick={testAd} disabled={busy} sx={{ ml: 1 }}>Test connection</Button>
                <Button variant="contained" onClick={next} sx={{ ml: 1 }}>Continue</Button>
                <Button onClick={back} sx={{ ml: 1 }}>Back</Button>
              </Box>
            </StepContent>
          </Step>

          {/* 3. Horizon Connection Server */}
          <Step>
            <StepLabel>Add a Horizon Connection Server (RADIUS client)</StepLabel>
            <StepContent>
              <TextField label="Name" fullWidth margin="dense" value={client.name}
                onChange={(e) => setClient({ ...client, name: e.target.value })}
                helperText="e.g. Horizon-CS01" />
              <TextField label="IP address" fullWidth margin="dense" value={client.ipaddr}
                onChange={(e) => setClient({ ...client, ipaddr: e.target.value })} />
              <TextField label="Shared secret" type="password" fullWidth margin="dense"
                value={client.shared_secret}
                onChange={(e) => setClient({ ...client, shared_secret: e.target.value })} />
              <Box sx={{ mt: 1 }}>
                <Button variant="contained" onClick={addClient}
                  disabled={busy || !client.name || !client.ipaddr || !client.shared_secret}>
                  Add &amp; continue</Button>
                <Button onClick={next} sx={{ ml: 1 }}>Skip</Button>
                <Button onClick={back} sx={{ ml: 1 }}>Back</Button>
              </Box>
            </StepContent>
          </Step>

          {/* 4. Allowed AD group */}
          <Step>
            <StepLabel>Allow an AD group</StepLabel>
            <StepContent>
              <TextField label="Name" fullWidth margin="dense" value={group.name}
                onChange={(e) => setGroup({ ...group, name: e.target.value })}
                helperText="e.g. Horizon-Users" />
              <TextField label="Group DN" fullWidth margin="dense" value={group.group_dn}
                onChange={(e) => setGroup({ ...group, group_dn: e.target.value })}
                helperText="CN=Horizon-Users,OU=Groups,DC=corp,DC=example,DC=local" />
              <Box sx={{ mt: 1 }}>
                <Button variant="contained" onClick={addGroup}
                  disabled={busy || !group.name || !group.group_dn}>Add &amp; continue</Button>
                <Button onClick={next} sx={{ ml: 1 }}>Skip</Button>
                <Button onClick={back} sx={{ ml: 1 }}>Back</Button>
              </Box>
            </StepContent>
          </Step>

          {/* 5. Activate */}
          <Step>
            <StepLabel>Generate &amp; activate the configuration</StepLabel>
            <StepContent>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Builds the FreeRADIUS config from your settings, validates it, and reloads.
              </Typography>
              <Button variant="contained" onClick={activate} disabled={busy}>Generate, validate &amp; activate</Button>
              <Button onClick={next} sx={{ ml: 1 }}>Continue</Button>
              <Button onClick={back} sx={{ ml: 1 }}>Back</Button>
            </StepContent>
          </Step>

          {/* 6. Test authentication */}
          <Step>
            <StepLabel>Test authentication</StepLabel>
            <StepContent>
              <TextField label="Username" fullWidth margin="dense" value={test.username}
                onChange={(e) => setTest({ ...test, username: e.target.value })} />
              <TextField label="Passcode" type="password" fullWidth margin="dense"
                value={test.password}
                onChange={(e) => setTest({ ...test, password: e.target.value })}
                helperText="AD password (LDAP), OTP (MFA totp_only), or password+OTP" />
              <Box sx={{ mt: 1 }}>
                <Button variant="contained" onClick={runTest}
                  disabled={busy || !test.username || !test.password}>Test</Button>
                <Button onClick={next} sx={{ ml: 1 }}>Continue</Button>
                <Button onClick={back} sx={{ ml: 1 }}>Back</Button>
              </Box>
            </StepContent>
          </Step>

          {/* 7. Finish */}
          <Step>
            <StepLabel>Finish</StepLabel>
            <StepContent>
              <Alert severity="success" sx={{ mb: 2 }}>
                <Chip label="✓ FreeRADIUS is ready for Horizon" color="success" sx={{ mr: 1 }} />
                Mark setup complete and go to the dashboard.
              </Alert>
              <Button variant="contained" color="success" onClick={finish} disabled={busy}>
                Finish setup</Button>
              <Button onClick={back} sx={{ ml: 1 }}>Back</Button>
            </StepContent>
          </Step>
        </Stepper>
      </Paper>
    </Box>
  );
}
