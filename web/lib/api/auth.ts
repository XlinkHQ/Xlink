import { apiFetch, clearTokens, getRefreshToken, setTokens } from "./core";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type AuthUser = {
  id: string;
  email: string;
  username: string;
  role: string;
};

export type AuthResponse = {
  user: AuthUser;
  tokens: TokenPair;
};

export async function login(
  identifier: string,
  password: string,
  totpCode?: string,
): Promise<AuthResponse> {
  const data = await apiFetch<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ identifier, password, totp_code: totpCode || null }),
  });
  setTokens(data.tokens);
  return data;
}

export function totpEnroll() {
  return apiFetch<{ secret: string; otpauth_uri: string }>("/auth/2fa/enroll", { method: "POST" });
}

export function totpConfirm(code: string) {
  return apiFetch<void>("/auth/2fa/confirm", { method: "POST", body: JSON.stringify({ code }) });
}

export function totpDisable(code: string) {
  return apiFetch<void>("/auth/2fa/disable", { method: "POST", body: JSON.stringify({ code }) });
}

export async function logout(): Promise<void> {
  const refresh = getRefreshToken();
  if (refresh) {
    try {
      await apiFetch("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refresh }),
      });
    } catch {
    }
  }
  clearTokens();
}

export function logoutAll() {
  return apiFetch<void>("/auth/logout-all", { method: "POST" });
}
