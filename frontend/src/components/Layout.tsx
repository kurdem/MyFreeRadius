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
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import RouterIcon from "@mui/icons-material/Router";
import GroupWorkIcon from "@mui/icons-material/GroupWork";
import SettingsEthernetIcon from "@mui/icons-material/SettingsEthernet";
import ArticleIcon from "@mui/icons-material/Article";
import BackupIcon from "@mui/icons-material/Backup";
import DomainIcon from "@mui/icons-material/Domain";
import VpnKeyIcon from "@mui/icons-material/VpnKey";
import PolicyIcon from "@mui/icons-material/Policy";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import ScienceIcon from "@mui/icons-material/Science";
import PeopleIcon from "@mui/icons-material/People";
import PaletteIcon from "@mui/icons-material/Palette";
import MonitorHeartIcon from "@mui/icons-material/MonitorHeart";
import LogoutIcon from "@mui/icons-material/Logout";
import { useAuth } from "../auth/AuthContext";
import { useBranding } from "../branding/useBranding";

const drawerWidth = 240;

interface NavItem {
  label: string;
  to: string;
  icon: ReactNode;
  soon?: boolean;
  adminOnly?: boolean;
}

const navItems: NavItem[] = [
  { label: "Dashboard", to: "/", icon: <DashboardIcon /> },
  { label: "Setup Wizard", to: "/wizard", icon: <AutoFixHighIcon /> },
  { label: "RADIUS Clients", to: "/clients", icon: <RouterIcon /> },
  { label: "Client Groups", to: "/client-groups", icon: <GroupWorkIcon /> },
  { label: "Configuration", to: "/configuration", icon: <SettingsEthernetIcon /> },
  { label: "Logs", to: "/logs", icon: <ArticleIcon /> },
  { label: "Active Directory", to: "/active-directory", icon: <DomainIcon /> },
  { label: "MFA", to: "/mfa", icon: <VpnKeyIcon /> },
  { label: "Policies", to: "/policies", icon: <PolicyIcon /> },
  { label: "Test Auth", to: "/test-auth", icon: <ScienceIcon /> },
  { label: "Certificates", to: "/certificates", icon: <VerifiedUserIcon /> },
  { label: "Backup", to: "/backup", icon: <BackupIcon /> },
  { label: "Monitoring", to: "/monitoring", icon: <MonitorHeartIcon /> },
  { label: "Users", to: "/users", icon: <PeopleIcon />, adminOnly: true },
  { label: "Branding", to: "/branding", icon: <PaletteIcon />, adminOnly: true },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout, isAdmin } = useAuth();
  const branding = useBranding();
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
        {navItems.filter((item) => !item.adminOnly || isAdmin).map((item) => (
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
          {branding.logoUrl && (
            <Box
              component="img"
              src={branding.logoUrl}
              alt="Logo"
              sx={{ height: 32, mr: 1.5, bgcolor: "white", borderRadius: 0.5, p: 0.25 }}
            />
          )}
          <Typography variant="h6" sx={{ flexGrow: 1 }} noWrap>
            {branding.title}
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
