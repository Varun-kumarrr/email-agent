// Stores the JWT for this assignment in localStorage with its expiry time.
// Trade-off: simple and works with a separate API origin, but readable by any
// script on the page, so XSS must be prevented (React escapes output by default
// and we never render raw HTML). A production system would prefer an
// HttpOnly, Secure, SameSite cookie set by the backend.

const TOKEN_KEY = "email_agent_token";
const EXPIRES_KEY = "email_agent_token_expires_at";

export function saveSession(token: string, expiresInSeconds: number): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EXPIRES_KEY, String(Date.now() + expiresInSeconds * 1000));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = localStorage.getItem(TOKEN_KEY);
  const expiresAt = Number(localStorage.getItem(EXPIRES_KEY) || 0);
  if (!token || Date.now() >= expiresAt) {
    clearSession();
    return null;
  }
  return token;
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EXPIRES_KEY);
}
