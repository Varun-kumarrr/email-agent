"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, Field, LoadingScreen, PageHeader, SubmitButton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { isEmail } from "@/lib/emails";
import type { EmailAccount, EmailAccountCreate, EmailProviderName, SecurityType, SmtpTestResult } from "@/lib/types";

const PROVIDERS: { value: EmailProviderName; label: string; hint: string }[] = [
  { value: "GMAIL", label: "Gmail (SMTP)", hint: "smtp.gmail.com:587 STARTTLS — requires a Google App Password, not your normal password." },
  { value: "OUTLOOK", label: "Outlook / Microsoft 365 (SMTP)", hint: "smtp.office365.com:587 STARTTLS — SMTP AUTH must be enabled for the mailbox." },
  { value: "GENERIC", label: "Other SMTP server", hint: "Any public SMTP provider (Zoho, Mailtrap, your host, …)." },
];

const SECURITY_OPTIONS: { value: SecurityType; label: string }[] = [
  { value: "STARTTLS", label: "STARTTLS (usually 587)" },
  { value: "SSL_TLS", label: "SSL/TLS (usually 465)" },
  { value: "NONE", label: "None (usually 25, not recommended)" },
];

interface FormState {
  account_name: string;
  provider: EmailProviderName;
  email_address: string;
  sender_name: string;
  reply_to: string;
  smtp_host: string;
  smtp_port: string;
  smtp_username: string;
  security_type: SecurityType;
  password: string;
  is_default: boolean;
}

const EMPTY: FormState = {
  account_name: "",
  provider: "GMAIL",
  email_address: "",
  sender_name: "",
  reply_to: "",
  smtp_host: "",
  smtp_port: "587",
  smtp_username: "",
  security_type: "STARTTLS",
  password: "",
  is_default: false,
};

function fromAccount(a: EmailAccount): FormState {
  return {
    account_name: a.account_name,
    provider: a.provider,
    email_address: a.email_address,
    sender_name: a.sender_name,
    reply_to: a.reply_to ?? "",
    smtp_host: a.smtp_host ?? "",
    smtp_port: a.smtp_port ? String(a.smtp_port) : "",
    smtp_username: a.smtp_username ?? "",
    security_type: a.security_type ?? "STARTTLS",
    password: "",
    is_default: a.is_default,
  };
}

const providerLabel = (a: EmailAccount) =>
  a.account_type === "OAUTH"
    ? a.provider === "GMAIL"
      ? "Gmail (OAuth)"
      : "Outlook (OAuth)"
    : (PROVIDERS.find((p) => p.value === a.provider)?.label ?? a.provider);

export default function EmailAccountsPage() {
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [noCompany, setNoCompany] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState<EmailAccount | "new" | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [testRecipient, setTestRecipient] = useState("");
  const [testResults, setTestResults] = useState<Record<string, SmtpTestResult>>({});

  const reload = useCallback(async () => {
    try {
      setAccounts(await api.listEmailAccounts());
    } catch (err) {
      if (isMissingCompany(err)) setNoCompany(true);
      else setError(err instanceof ApiError ? err.message : "Could not load email accounts.");
    }
  }, []);

  useEffect(() => {
    reload().finally(() => setLoading(false));
  }, [reload]);

  const set = (key: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value }));

  function startNew() {
    setEditing("new");
    setForm(EMPTY);
    setErrors({});
    setSuccess("");
    setError("");
  }

  function startEdit(account: EmailAccount) {
    setEditing(account);
    setForm(fromAccount(account));
    setErrors({});
    setSuccess("");
    setError("");
  }

  const isNew = editing === "new";
  const isOauth = editing !== null && editing !== "new" && editing.account_type === "OAUTH";
  const needsServer = !isOauth && (form.provider === "GENERIC" || !isNew);

  function validate(): Record<string, string> {
    const e: Record<string, string> = {};
    if (!form.account_name.trim()) e.account_name = "Give the account a name";
    if (!isOauth && !isEmail(form.email_address)) e.email_address = "Enter a valid email address";
    if (!form.sender_name.trim()) e.sender_name = "Sender name is required";
    if (form.reply_to.trim() && !isEmail(form.reply_to)) e.reply_to = "Enter a valid email address";
    if (needsServer) {
      if (!form.smtp_host.trim() || /[:/\s]/.test(form.smtp_host.trim())) e.smtp_host = "Host name only, e.g. smtp.zoho.com";
      const port = Number(form.smtp_port);
      if (!Number.isInteger(port) || port < 1 || port > 65535) e.smtp_port = "Port must be 1–65535";
    }
    if (isNew && !form.password) e.password = "Password / app password is required";
    return e;
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const clientErrors = validate();
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length || editing === null) return;

    setSaving(true);
    try {
      if (isNew) {
        const payload: EmailAccountCreate = {
          account_name: form.account_name.trim(),
          provider: form.provider,
          email_address: form.email_address.trim(),
          sender_name: form.sender_name.trim(),
          reply_to: form.reply_to.trim() || null,
          smtp_username: form.smtp_username.trim() || null,
          password: form.password,
          is_default: form.is_default,
        };
        if (needsServer) {
          payload.smtp_host = form.smtp_host.trim();
          payload.smtp_port = Number(form.smtp_port);
          payload.security_type = form.security_type;
        }
        await api.createEmailAccount(payload);
        setSuccess("Email account added. Send a test email to verify it.");
      } else {
        const update: Parameters<typeof api.updateEmailAccount>[1] = {
          account_name: form.account_name.trim(),
          sender_name: form.sender_name.trim(),
          reply_to: form.reply_to.trim() || null,
        };
        if (!isOauth) {
          update.email_address = form.email_address.trim();
          update.smtp_host = form.smtp_host.trim();
          update.smtp_port = Number(form.smtp_port);
          update.smtp_username = form.smtp_username.trim();
          update.security_type = form.security_type;
          if (form.password) update.password = form.password; // blank keeps the stored one
        }
        await api.updateEmailAccount(editing.id, update);
        setSuccess("Email account updated.");
      }
      setEditing(null);
      setForm(EMPTY); // clears the password field
      await reload();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setError(err.message);
      } else setError("Could not save the email account.");
    } finally {
      setSaving(false);
    }
  }

  async function act(id: string, action: () => Promise<unknown>, message: string) {
    setBusy(id);
    setError("");
    setSuccess("");
    try {
      await action();
      setSuccess(message);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The action failed.");
    } finally {
      setBusy(null);
    }
  }

  async function runTest(account: EmailAccount) {
    const recipient = testRecipient.trim() || account.email_address;
    if (!isEmail(recipient)) {
      setError("Enter a valid test recipient address.");
      return;
    }
    setBusy(account.id);
    setError("");
    try {
      const result = await api.testEmailAccount(account.id, recipient);
      setTestResults((r) => ({ ...r, [account.id]: result }));
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The test could not be run.");
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <LoadingScreen />;
  if (noCompany) {
    return (
      <>
        <PageHeader title="Email Accounts" />
        <NeedsCompany />
      </>
    );
  }

  const input = (key: keyof FormState, label: string, opts: { type?: string; hint?: string; placeholder?: string; disabled?: boolean } = {}) => (
    <Field label={label} htmlFor={key} error={errors[key]} hint={opts.hint}>
      <input
        id={key}
        type={opts.type ?? "text"}
        value={String(form[key])}
        onChange={set(key)}
        placeholder={opts.placeholder}
        disabled={opts.disabled}
        autoComplete={opts.type === "password" ? "new-password" : "off"}
        className={errors[key] ? "invalid" : ""}
      />
    </Field>
  );

  return (
    <>
      <PageHeader
        title="Email Accounts"
        description="Mailboxes your company sends from. Each email is sent through the account you choose — never a shared system account."
      />
      <Alert kind="success">{success}</Alert>
      <Alert kind="error">{error}</Alert>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Your accounts</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn" onClick={startNew}>
              + Add SMTP account
            </button>
          </div>
        </div>
        {accounts.length === 0 ? (
          <p className="muted">No email accounts yet. Add one to start sending.</p>
        ) : (
          <>
            <div className="list-row" style={{ marginTop: 14, maxWidth: 520 }}>
              <input
                aria-label="Test recipient"
                type="email"
                placeholder="Test recipient (defaults to the account's own address)"
                value={testRecipient}
                onChange={(e) => setTestRecipient(e.target.value)}
              />
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Provider</th>
                    <th>Status</th>
                    <th>Credentials</th>
                    <th>Last test</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <strong>{a.account_name}</strong>
                        <div className="muted">{a.sender_name} &lt;{a.email_address}&gt;</div>
                      </td>
                      <td>{providerLabel(a)}</td>
                      <td>
                        {a.is_default && <span className="badge badge-info" style={{ marginRight: 4 }}>Default</span>}
                        <span className={`badge ${a.is_active ? "badge-success" : ""}`}>{a.is_active ? "Active" : "Inactive"}</span>
                      </td>
                      <td>
                        {a.account_type === "SMTP"
                          ? `Password configured: ${a.password_configured ? "Yes" : "No"}`
                          : `OAuth connected: ${a.oauth_connected ? "Yes" : "No"}`}
                      </td>
                      <td>
                        {a.last_test_success === null ? (
                          <span className="badge">Not tested</span>
                        ) : a.last_test_success ? (
                          <span className="badge badge-success">Passed</span>
                        ) : (
                          <span className="badge badge-danger">Failed</span>
                        )}
                        {testResults[a.id] && (
                          <div className={testResults[a.id].success ? "muted" : "error"} style={{ fontSize: "0.82rem", maxWidth: 260 }}>
                            {testResults[a.id].message}
                          </div>
                        )}
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          <button className="btn btn-secondary btn-small" disabled={busy === a.id} onClick={() => runTest(a)}>
                            Test
                          </button>
                          {!a.is_default && a.is_active && (
                            <button
                              className="btn btn-secondary btn-small"
                              disabled={busy === a.id}
                              onClick={() => act(a.id, () => api.setDefaultEmailAccount(a.id), `${a.account_name} is now the default account.`)}
                            >
                              Set default
                            </button>
                          )}
                          <button
                            className="btn btn-secondary btn-small"
                            disabled={busy === a.id}
                            onClick={() =>
                              act(
                                a.id,
                                () => api.updateEmailAccount(a.id, { is_active: !a.is_active }),
                                a.is_active ? "Account deactivated." : "Account activated.",
                              )
                            }
                          >
                            {a.is_active ? "Deactivate" : "Activate"}
                          </button>
                          <button className="btn btn-secondary btn-small" onClick={() => startEdit(a)}>
                            Edit
                          </button>
                          <button
                            className="btn btn-danger btn-small"
                            disabled={busy === a.id}
                            onClick={() => {
                              if (window.confirm(`Delete ${a.account_name}? History keeps the sender address.`))
                                act(a.id, () => api.deleteEmailAccount(a.id), "Account deleted.");
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {editing !== null && (
        <form className="card" onSubmit={onSave} noValidate autoComplete="off">
          <h2>{isNew ? "Add SMTP account" : `Edit ${editing.account_name}`}</h2>
          <div className="grid grid-2">
            {isNew && (
              <Field label="Provider" htmlFor="provider" hint={PROVIDERS.find((p) => p.value === form.provider)?.hint} className="span-2">
                <select id="provider" value={form.provider} onChange={set("provider")}>
                  {PROVIDERS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {input("account_name", "Account name *", { placeholder: "Sales mailbox" })}
            {input("email_address", "Email address *", { type: "email", disabled: isOauth })}
            {input("sender_name", "Sender name *", { placeholder: "Anjali from ABC Technologies" })}
            {input("reply_to", "Reply-to email", { type: "email", hint: "Optional." })}
            {needsServer && (
              <>
                {input("smtp_host", "SMTP host *", { placeholder: "smtp.example.com" })}
                {input("smtp_port", "SMTP port *", { type: "number" })}
                <Field label="Security *" htmlFor="security_type">
                  <select id="security_type" value={form.security_type} onChange={set("security_type")}>
                    {SECURITY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </Field>
              </>
            )}
            {!isOauth && input("smtp_username", "SMTP username", { hint: "Defaults to the email address." })}
            {!isOauth &&
              input("password", isNew ? "Password / app password *" : "Password / app password", {
                type: "password",
                hint: isNew
                  ? "Stored encrypted and never shown again. Gmail needs an App Password."
                  : "Leave blank to keep the saved password.",
              })}
            {isNew && (
              <label className="checkbox span-2">
                <input type="checkbox" checked={form.is_default} onChange={set("is_default")} />
                Make this the default sending account
              </label>
            )}
          </div>
          <div className="form-actions">
            <SubmitButton loading={saving}>{isNew ? "Add account" : "Save changes"}</SubmitButton>
            <button type="button" className="btn btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </>
  );
}
