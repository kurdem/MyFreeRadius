import { Navigate, Route, Routes } from "react-router-dom";
import { CircularProgress, Box } from "@mui/material";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Clients from "./pages/Clients";
import ClientGroups from "./pages/ClientGroups";
import Configuration from "./pages/Configuration";
import Logs from "./pages/Logs";
import ActiveDirectory from "./pages/ActiveDirectory";
import Mfa from "./pages/Mfa";
import TestAuth from "./pages/TestAuth";
import Certificates from "./pages/Certificates";
import Backup from "./pages/Backup";
import Wizard from "./pages/Wizard";
import Users from "./pages/Users";
import ComingSoon from "./pages/ComingSoon";
import type { ReactNode } from "react";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 8 }}>
        <CircularProgress />
      </Box>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/clients" element={<Protected><Clients /></Protected>} />
      <Route path="/client-groups" element={<Protected><ClientGroups /></Protected>} />
      <Route path="/configuration" element={<Protected><Configuration /></Protected>} />
      <Route path="/logs" element={<Protected><Logs /></Protected>} />
      <Route path="/active-directory" element={<Protected><ActiveDirectory /></Protected>} />
      <Route path="/mfa" element={<Protected><Mfa /></Protected>} />
      <Route
        path="/policies"
        element={
          <Protected>
            <ComingSoon
              title="Authentication Policies"
              phase="Phase 4"
              description="Policy engine mapping RADIUS client groups + AD groups to allow/deny decisions and reply attributes."
            />
          </Protected>
        }
      />
      <Route path="/certificates" element={<Protected><Certificates /></Protected>} />
      <Route path="/backup" element={<Protected><Backup /></Protected>} />
      <Route path="/wizard" element={<Protected><Wizard /></Protected>} />
      <Route path="/users" element={<Protected><Users /></Protected>} />
      <Route path="/test-auth" element={<Protected><TestAuth /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
