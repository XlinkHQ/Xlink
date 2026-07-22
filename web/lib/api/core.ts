const TOKEN_KEY = "xlink.access_token";
const REFRESH_KEY = "xlink.refresh_token";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(tokens: { access_token: string; refresh_token: string }): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

let refreshInFlight: Promise<string | null> | null = null;
let onAuthLost: (() => void) | null = null;

export function setAuthLostHandler(handler: (() => void) | null): void {
  onAuthLost = handler;
}

async function performRefresh(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  try {
    const response = await fetch(`/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!response.ok) {
      clearTokens();
      return null;
    }
    const tokens = (await response.json()) as { access_token: string; refresh_token: string };
    setTokens(tokens);
    return tokens.access_token;
  } catch (err) {
    // A network failure (offline blip) is NOT an auth rejection — rethrow so the
    // caller surfaces a retryable error instead of clearing a still-valid
    // refresh token and force-logging the admin out. Only a non-ok response
    // above (handled) means the refresh token is actually dead.
    throw err;
  }
}

function refreshTokens(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function readError(response: Response): Promise<{ message: string; code?: string }> {
  try {
    const body = await response.json();
    const code = typeof body?.error?.code === "string" ? body.error.code : undefined;
    if (typeof body?.error?.message === "string") return { message: body.error.message, code };
    if (typeof body?.detail === "string") return { message: body.detail, code };
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      const d = body.detail[0];
      const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
      return { message: field ? `${field}: ${d.msg}` : d.msg, code };
    }
    if (typeof body?.message === "string") return { message: body.message, code };
  } catch {
    // body is not JSON
  }
  return { message: response.statusText || `Request failed (${response.status})` };
}

const NO_REFRESH_PATHS = ["/auth/login", "/auth/refresh", "/auth/register"];

const REQUEST_TIMEOUT_MS = 45000;

async function rawFetch(path: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  // Don't force a JSON Content-Type on FormData uploads — the browser must set
  // the multipart boundary itself.
  if (init.body && !headers.has("Content-Type") && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  // Abort on timeout so a hung backend call rejects instead of leaving mutation
  // dialogs stuck on their "Adding…"/"Saving…" spinner forever (busy only resets
  // in finally, which never runs if the promise never settles).
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(`/api/v1${path}`, { ...init, headers, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Request timed out. Please try again.", 408, "timeout");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function ensureAuthed(path: string, init: RequestInit): Promise<Response> {
  let response = await rawFetch(path, init, getToken());

  if (
    response.status === 401 &&
    !NO_REFRESH_PATHS.some((p) => path.startsWith(p)) &&
    getRefreshToken()
  ) {
    const fresh = await refreshTokens();
    if (fresh) {
      response = await rawFetch(path, init, fresh);
    } else {
      clearTokens();
      onAuthLost?.();
      throw new ApiError("Session expired. Please sign in again.", 401);
    }
  }

  return response;
}

// Like apiFetch but returns the raw Response (for blob/CSV downloads and file
// uploads). Routes through ensureAuthed so a 401 after an idle tab triggers the
// same token refresh every other request gets, instead of failing outright.
export async function apiFetchRaw(path: string, init: RequestInit = {}): Promise<Response> {
  return ensureAuthed(path, init);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await ensureAuthed(path, init);

  if (!response.ok) {
    if (response.status === 401) {
      clearTokens();
      onAuthLost?.();
    }
    const e = await readError(response);
    throw new ApiError(e.message, response.status, e.code);
  }
  if (response.status === 204) {
    return undefined as unknown as T;
  }
  return (await response.json()) as T;
}

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
  size: number;
};
