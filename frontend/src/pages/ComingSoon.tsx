import { Alert, Box, Chip, Paper, Stack, Typography } from "@mui/material";
import ConstructionIcon from "@mui/icons-material/Construction";

interface Props {
  title: string;
  phase: string;
  description: string;
}

/** Honest placeholder for not-yet-implemented features (spec section 40). */
export default function ComingSoon({ title, phase, description }: Props) {
  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h4">{title}</Typography>
        <Chip icon={<ConstructionIcon />} label={`Coming Soon - ${phase}`} color="warning" />
      </Stack>
      <Paper sx={{ p: 3, maxWidth: 720 }}>
        <Alert severity="info" sx={{ mb: 2 }}>
          This feature is planned but not implemented yet. It is shown here so the
          navigation reflects the full roadmap - it does not perform any action.
        </Alert>
        <Typography variant="body1">{description}</Typography>
      </Paper>
    </Box>
  );
}
