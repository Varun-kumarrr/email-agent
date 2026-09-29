"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, Badge, Card, CardHeader, Field, LoadingScreen, PageHeader, SubmitButton } from "@/components/ui";
import { api, ApiError, isNotFound } from "@/lib/api";
import type { EmailConfig, EmailConfigInput, SecurityType, SmtpTestResult } from "@/lib/types";

const DEFAULT_PORTS: Record<SecurityType, number> = { STARTTLS: 587, SSL_TLS: 465, NONE: 25 };

const SECURITY_LABELS: Record<SecurityType, string> = {
  STARTTLS: "STARTTLS (usually port 587)",
  SSL_TLS: "SSL/TLS (usually port 465)",
  NONE: "None — unencrypted (usually port 25, not recommended)",
};

interface FormState {
  email: string;
  smtp_host: string;
  smtp_port: string;
  username: string;
  password: string; // only ever typed by the user; never loaded from the server
  security_type: SecurityType;
  sender_name: string;
  reply_to: string;
}

const EMPTY: FormState = {
  email: "",
  smtp_host: "",
  smtp_port: "587",
  username: "",
  password: "",
  security_type: "STARTTLS",
  sender_name: "",
  reply_to: "",
};

function fromConfig(c: EmailConfig): FormState {
  return {
    email: c.email,
    smtp_host: c.smtp_host,
    smtp_port: String(c.smtp_port),
    username: c.username,
    password: "",
    security_type: c.security_type,
    sender_name: c.sender_name,
    reply_to: c.reply_to ?? "",
  };
}

function validate(f: FormState, creating: boolean): Record<string, string> {
  const errors: Record<string, string> = {};
  const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRe.test(f.email.trim())) errors.email = "Enter a valid email address";
  if (!f.smtp_host.trim()) errors.smtp_host = "SMTP host is required";
  else if (/[:/\s]/.test(f.smtp_host.trim())) errors.smtp_host = "Host name only, e.g. smtp.gmail.com";
  const port = Number(f.smtp_port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) errors.smtp_port = "Port must be 1–65535";
  if (!f.username.trim()) errors.username = "Username is required";
  if (creating && !f.password) errors.password = "Password / app password is required";
  if (!f.sender_name.trim()) errors.sender_name = "Sender name is required";
  if (f.reply_to.trim() && !emailRe.test(f.reply_to.trim())) errors.reply_to = "Enter a valid email address";
  return errors;
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "";
}

export default function EmailConfigPage() {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [config, setConfig] = useState<EmailConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [noCompany, setNoCompany] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [testRecipient, setTestRecipient] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<SmtpTestResult | null>(null);
  const [testError, setTestError] = useState("");

  useEffect(() => {
    api
      .getEmailConfig()
      .then((c) => {
        setConfig(c);
        setForm(fromConfig(c));
        setTestRecipient(c.email);
      })
      .catch((err) => {
        if (isMissingCompany(err)) setNoCompany(true);
        else if (!isNotFound(err)) setError(err instanceof ApiError ? err.message : "Could not load settings.");
      })
      .finally(() => setLoading(false));
  }, []);

  const set = (key: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  function onSecurityChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const security_type = e.target.value as SecurityType;
    setForm((f) => {
      // Suggest the conventional port if the current one is one of the defaults.
      const usingDefault = Object.values(DEFAULT_PORTS).includes(Number(f.smtp_port));
      return { ...f, security_type, smtp_port: usingDefault ? String(DEFAULT_PORTS[security_type]) : f.smtp_port };
    });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const clientErrors = validate(form, !config);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    const payload: EmailConfigInput = {
      email: form.email.trim(),
      smtp_host: form.smtp_host.trim(),
      smtp_port: Number(form.smtp_port),
      username: form.username.trim(),
      security_type: form.security_type,
      sender_name: form.sender_name.trim(),
      reply_to: form.reply_to.trim() || null,
    };
    // Only send a password when the user typed one; omitted = keep the stored one.
    if (form.password) payload.password = form.password;

    setSaving(true);
    try {
      const saved = config ? await api.updateEmailConfig(payload) : await api.createEmailConfig(payload);
      setConfig(saved);
      setForm(fromConfig(saved)); // clears the password field
      if (!testRecipient) setTestRecipient(saved.email);
      setSuccess("Email configuration saved. Send a test email to verify it.");
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setError(err.message);
      } else {
        setError("Could not save the configuration.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    setTestResult(null);
    setTestError("");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(testRecipient.trim())) {
      setTestError("Enter a valid recipient email address");
      return;
    }
    setTesting(true);
    try {
      const result = await api.testEmailConfig(testRecipient.trim());
      setTestResult(result);
      setConfig((c) => (c ? { ...c, last_tested_at: result.tested_at, last_test_success: result.success } : c));
    } catch (err) {
      setTestError(err instanceof ApiError ? err.message : "The test could not be run.");
    } finally {
      setTesting(false);
    }
  }

  const header = (
    <PageHeader
      title="Email Configuration"
      description="Your company's primary SMTP account. All emails are sent from your own accounts — there is no shared system sender."
    />
  );

  if (loading)
    return (
      <>
        {header}
        <LoadingScreen />
      </>
    );
  if (noCompany) {
    return (
      <>
        {header}
        <NeedsCompany />
      </>
    );
  }

  const input = (key: keyof FormState, label: string, opts: { type?: string; hint?: string; placeholder?: string; autoComplete?: string } = {}) => (
    <Field label={label} htmlFor={key} error={errors[key]} hint={opts.hint}>
      <input
        id={key}
        type={opts.type ?? "text"}
        value={form[key]}
        onChange={set(key)}
        placeholder={opts.placeholder}
        autoComplete={opts.autoComplete ?? "off"}
        className={errors[key] ? "invalid" : ""}
      />
    </Field>
  );

  return (
    <>
      {header}
      <Alert kind="info">
        This page edits your primary SMTP account. To add more accounts (Gmail, Outlook, other SMTP servers) or choose the default, use{" "}
        <Link href="/email-accounts">Email Accounts</Link>.
      </Alert>
      <Alert kind="success">{success}</Alert>
      <Alert kind="error">{error}</Alert>

      {config && (
        <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <p className="text-[11px] font-semibold tracking-wider text-slate-500 uppercase">Password configured</p>
            <p className="mt-1 font-semibold text-slate-900">{config.password_configured ? "Yes" : "No"}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <p className="text-[11px] font-semibold tracking-wider text-slate-500 uppercase">Last test</p>
            <div className="mt-1">
              {config.last_test_success === null ? (
                <Badge>Not tested</Badge>
              ) : config.last_test_success ? (
                <Badge tone="success">Passed</Badge>
              ) : (
                <Badge tone="danger">Failed</Badge>
              )}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <p className="text-[11px] font-semibold tracking-wider text-slate-500 uppercase">Tested at</p>
            <p className="mt-1 font-semibold text-slate-900">{formatDate(config.last_tested_at) || "—"}</p>
          </div>
        </div>
      )}

      <Card>
        <form onSubmit={onSubmit} noValidate autoComplete="off">
          <CardHeader icon="server" title="SMTP account" />
          <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
            {input("email", "Email address *", { type: "email", placeholder: "you@company.com" })}
            {input("sender_name", "Sender name *", { placeholder: "Anjali from ABC Technologies" })}
            {input("smtp_host", "SMTP host *", { placeholder: "smtp.gmail.com" })}
            {input("smtp_port", "SMTP port *", { type: "number" })}
            <Field label="Security *" htmlFor="security_type" error={errors.security_type}>
              <select id="security_type" value={form.security_type} onChange={onSecurityChange}>
                {(Object.keys(SECURITY_LABELS) as SecurityType[]).map((key) => (
                  <option key={key} value={key}>
                    {SECURITY_LABELS[key]}
                  </option>
                ))}
              </select>
            </Field>
            {input("username", "Username *", { placeholder: "Usually your email address" })}
            {input("password", config ? "Password / app password" : "Password / app password *", {
              type: "password",
              autoComplete: "new-password",
              placeholder: config?.password_configured ? "•••••••• (leave blank to keep current)" : "",
              hint: config
                ? "Leave blank to keep the saved password. It is stored encrypted and never shown again."
                : "Stored encrypted. It is never shown again after saving. Gmail/Outlook need an app password.",
            })}
            {input("reply_to", "Reply-to email", { type: "email", hint: "Optional. Replies go here instead of the sender address." })}
          </div>
          <div className="flex justify-end border-t border-slate-100 px-5 py-3.5">
            <SubmitButton loading={saving}>{config ? "Save changes" : "Save configuration"}</SubmitButton>
          </div>
        </form>
      </Card>

      <Card className="mt-5">
        <CardHeader
          icon="send"
          title="Test email configuration"
          description={`Sends a real test email through the saved SMTP settings${config ? "" : " (save them first)"}.`}
        />
        <div className="space-y-3 p-5">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              aria-label="Test recipient"
              type="email"
              placeholder="recipient@example.com"
              value={testRecipient}
              onChange={(e) => setTestRecipient(e.target.value)}
              disabled={!config}
            />
            <SubmitButton type="button" loading={testing} disabled={!config} onClick={onTest}>
              Test Email Configuration
            </SubmitButton>
          </div>
          <Alert kind="error">{testError}</Alert>
          {testResult && (
            <Alert kind={testResult.success ? "success" : "error"}>
              {testResult.message}
              {testResult.error_code ? ` (${testResult.error_code})` : ""}
            </Alert>
          )}
        </div>
      </Card>
    </>
  );
}
