import { useEffect, useState } from "react";
import { api } from "../api/client";

export interface Branding {
  title: string;
  logoUrl: string | null;
}

const DEFAULT_TITLE = "FreeRADIUS Manager";

/** Fetch the configurable branding (title + logo). Public endpoint. */
export function useBranding(): Branding {
  const [branding, setBranding] = useState<Branding>({ title: DEFAULT_TITLE, logoUrl: null });

  useEffect(() => {
    api
      .get<{ app_title: string; has_logo: boolean }>("/branding")
      .then((r) =>
        setBranding({
          title: r.data.app_title || DEFAULT_TITLE,
          // Cache-bust so an updated logo shows immediately after a reload.
          logoUrl: r.data.has_logo ? `/api/v1/branding/logo?ts=${Date.now()}` : null,
        }),
      )
      .catch(() => setBranding({ title: DEFAULT_TITLE, logoUrl: null }));
  }, []);

  return branding;
}
