// Single API client for the FastAPI backend.
// - Base URL from NEXT_PUBLIC_API_URL (a public URL, never a secret).
// - Attaches the JWT as `Authorization: Bearer <token>`.
// - Normalizes every failure into ApiError using the backend's error shape.
// - On 401 clears the session and notifies the app so it can redirect to /login.

import { clearSession, getToken } from "./session";
import type {
  Company,
  CompanyInput,
  EmailConfig,
  EmailConfigInput,
  EmailHistoryPage,
  EmailStatus,
  FieldError,
  GeneratedEmail,
  GenerateEmailInput,
  Preferences,
  PreferencesInput,
  SendEmailInput,
  SendEmailResult,
  Signature,
  SignatureInput,
  SmtpTestResult,
  TokenResponse,
  User,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
export const UNAUTHORIZED_EVENT = "email-agent:unauthorized";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field-level validation messages (422), keyed by field path. */
  get fieldErrors(): Record<string, string> {
    if (this.status !== 422 || !Array.isArray(this.details)) return {};
    const result: Record<string, string> = {};
    for (const item of this.details as FieldError[]) {
      if (item?.field && !result[item.field]) result[item.field] = item.message.replace(/^Value error, /, "");
    }
    return result;
  }
}

const FRIENDLY_MESSAGES: Record<number, string> = {
  401: "Your session has expired. Please log in again.",
  403: "You do not have permission to do that.",
  404: "Not found.",
  422: "Please correct the highlighted fields.",
  500: "Something went wrong on the server. Please try again.",
};

type Options = { method?: string; body?: unknown; auth?: boolean };

async function request<T>(path: string, { method = "GET", body, auth = true }: Options = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the server. Check that the backend is running.");
  }

  if (response.status === 204) return undefined as T;

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error;
    const message =
      response.status === 422
        ? FRIENDLY_MESSAGES[422]
        : err?.message || FRIENDLY_MESSAGES[response.status] || `Request failed (${response.status})`;
    if (response.status === 401 && auth) {
      clearSession();
      if (typeof window !== "undefined") window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(response.status, err?.code || "http_error", message, err?.details ?? null);
  }
  return data as T;
}

export const api = {
  // Authentication
  register: (data: { name: string; email: string; password: string }) =>
    request<User>("/api/v1/auth/register", { method: "POST", body: data, auth: false }),
  login: (data: { email: string; password: string }) =>
    request<TokenResponse>("/api/v1/auth/login", { method: "POST", body: data, auth: false }),
  me: () => request<User>("/api/v1/auth/me"),

  // Company profile
  getCompany: () => request<Company>("/api/v1/company"),
  createCompany: (data: CompanyInput) => request<Company>("/api/v1/company", { method: "POST", body: data }),
  updateCompany: (data: CompanyInput) => request<Company>("/api/v1/company", { method: "PUT", body: data }),

  // Email configuration
  getEmailConfig: () => request<EmailConfig>("/api/v1/email-config"),
  createEmailConfig: (data: EmailConfigInput) =>
    request<EmailConfig>("/api/v1/email-config", { method: "POST", body: data }),
  updateEmailConfig: (data: EmailConfigInput) =>
    request<EmailConfig>("/api/v1/email-config", { method: "PUT", body: data }),
  testEmailConfig: (recipient: string) =>
    request<SmtpTestResult>("/api/v1/email-config/test", { method: "POST", body: { recipient } }),

  // Signature
  getSignature: () => request<Signature>("/api/v1/signature"),
  createSignature: (data: SignatureInput) => request<Signature>("/api/v1/signature", { method: "POST", body: data }),
  updateSignature: (data: SignatureInput) => request<Signature>("/api/v1/signature", { method: "PUT", body: data }),
  deleteSignature: () => request<void>("/api/v1/signature", { method: "DELETE" }),

  // Preferences
  getPreferences: () => request<Preferences>("/api/v1/preferences"),
  updatePreferences: (data: PreferencesInput) =>
    request<Preferences>("/api/v1/preferences", { method: "PUT", body: data }),

  // AI agent + sending
  generateEmail: (data: GenerateEmailInput) =>
    request<GeneratedEmail>("/api/v1/agent/generate-email", { method: "POST", body: data }),
  sendEmail: (data: SendEmailInput) => request<SendEmailResult>("/api/v1/emails/send", { method: "POST", body: data }),
  history: (page = 1, pageSize = 20, status?: EmailStatus) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) params.set("status", status);
    return request<EmailHistoryPage>(`/api/v1/emails/history?${params}`);
  },
};

/** True when the error means "this resource hasn't been created yet". */
export const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;
