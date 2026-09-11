import axios from "axios";

// Same-origin API. Cookies carry the session; the CSRF token is read from the
// non-httpOnly cookie and echoed as a header on state-changing requests.
export const api = axios.create({
  baseURL: "/api/v1",
  withCredentials: true,
});

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

api.interceptors.request.use((config) => {
  const method = (config.method || "get").toLowerCase();
  if (!["get", "head", "options"].includes(method)) {
    const csrf = readCookie("radiusmgr_csrf");
    if (csrf) {
      config.headers = config.headers ?? {};
      config.headers["X-CSRF-Token"] = csrf;
    }
  }
  return config;
});

export interface ApiError {
  detail: string;
}

export function errorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as ApiError | undefined;
    if (data?.detail) return data.detail;
    return err.message;
  }
  return "Unexpected error";
}
