import { useState, type ReactNode } from "react";
import { Link as RouterLink, useLocation } from "react-router-dom";
import {
  AppBar,
  Box,
  Chip,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Tooltip,
  Typography,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import RouterIcon from "@mui/icons-material/Router";
import GroupWorkIcon from "@mui/icons-material/GroupWork";
import SettingsEthernetIcon from "@mui/icons-material/SettingsEthernet";
import ArticleIcon from "@mui/icons-material/Article";
import DomainIcon from "@mui/icons-material/Domain";
import VpnKeyIcon from "@mui/icons-material/VpnKey";
import PolicyIcon from "@mui/icons-material/Policy";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import ScienceIcon from "@mui/icons-material/Science";
import LogoutIcon from "@mui/icons-material/Logout";
import { useAuth } from "../auth/AuthContext";

const drawerWidth = 240;

interface NavItem {
  label: string;
  to: string;
  icon: ReactNode;
  soon?: boolean;
}

const navItems: NavItem[] = [
  { label: "Dashboard", to: "/", icon: <DashboardIcon /> },
  { label: "RADIUS Clients", to: "/clients", icon: <RouterIcon /> },
  { label: "Client Groups", to: "/client-groups", icon: <GroupWorkIcon /> },
  { label: "Configuration", to: "/configuration", icon: <SettingsEthernetIcon /> },
  { label: "Logs", to: "/logs", icon: <ArticleIcon /> },
  { label: "Active Directory", to: "/active-directory", icon: <DomainIcon /> },
  { label: "MFA", to: "/mfa", icon: <VpnKeyIcon /> },
  { label: "Policies", to: "/policies", icon: <PolicyIcon />, soon: true },
  { label: "Test Auth", to: "/test-auth", icon: <ScienceIcon /> },
  { label: "Certificates", to: "/certificates", icon: <VerifiedUserIcon />, soon: true },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const drawer = (
    <Box>
      <Toolbar>
        <Typography variant="h6" noWrap sx={{ fontWeight: 700 }}>
          FreeRADIUS
        </Typography>
      </Toolbar>
      <Divider />
      <List>
        {navItems.map((item) => (
          <ListItemButton
            key={item.to}
            component={RouterLink}
            to={item.to}
            selected={location.pathname === item.to}
            onClick={() => setMobileOpen(false)}
          >
            <ListItemIcon>{item.icon}</ListItemIcon>
            <ListItemText primary={item.label} />
            {item.soon && <Chip size="small" label="Soon" color="default" />}
          </ListItemButton>
        ))}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: "flex" }}>
      <AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }} noWrap>
            FreeRADIUS Manager
          </Typography>
          {user && (
            <Chip
              label={`${user.username} (${user.role})`}
              color="secondary"
              sx={{ mr: 1 }}
            />
          )}
          <Tooltip title="Logout">
            <IconButton color="inherit" onClick={() => logout()}>
              <LogoutIcon />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          display: { xs: "none", sm: "block" },
          [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: "border-box" },
        }}
        open
      >
        <Toolbar />
        {drawer}
      </Drawer>

      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        sx={{ display: { xs: "block", sm: "none" } }}
      >
        {drawer}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 3, width: "100%" }}>
        <Toolbar />
        {children}
      </Box>
    </Box>
  );
}
