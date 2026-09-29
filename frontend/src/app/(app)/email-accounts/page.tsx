"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Icon } from "@/components/Icon";
import { Alert, Badge, buttonClass, Card, CardHeader, cx, EmptyState, Field, LoadingScreen, PageHeader, Spinner, SubmitButton } from "@/components/ui";
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

// Safe, fixed messages for the ?oauth=gmail&status=...&reason=... callback redirect.
const OAUTH_REASONS: Record<string, string> = {
  access_denied: "You cancelled the Google consent screen.",
  state_missing: "The connection link was incomplete. Please try again.",
  state_invalid: "The connection request was not recognised. Please start again from this page.",
  state_used: "This connection link was already used. Please start again.",
  state_expired: "The connection request expired. Please try again.",
  scope_missing: "Permission to send email was not granted. Tick “Send email on your behalf” on Google’s consent screen.",
  email_unverified: "Google did not confirm a verified email address for this account.",
  refresh_token_missing: "Google did not return long-term access. Remove the app at myaccount.google.com/permissions and connect again.",
  token_exchange_failed: "Google rejected the authorization. Please try connecting again.",
  account_mismatch: "Your session changed during the connection. Please log in and try again.",
};

function oauthBanner(params: URLSearchParams): { kind: "success" | "error"; text: string } | null {
  if (params.get("oauth") !== "gmail") return null;
  if (params.get("status") === "success") {
    return {
      kind: "success",
      text: params.get("reason") === "reconnected" ? "Gmail reconnected. Its access was refreshed." : "Gmail connected. Send a test email to verify it.",
    };
  }
  const reason = params.get("reason") ?? "";
  return { kind: "error", text: `Gmail connection failed: ${OAUTH_REASONS[reason] ?? "Please try again."}` };
}

export default function EmailAccountsPage() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <EmailAccountsContent />
    </Suspense>
  );
}

function EmailAccountsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const banner = oauthBanner(searchParams);
  const [connecting, setConnecting] = useState(false);
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

  async function connectGmail() {
    setConnecting(true);
    setError("");
    try {
      const { authorization_url } = await api.authorizeGmail();
      // Only ever navigate to Google's consent page.
      if (!authorization_url.startsWith("https://accounts.google.com/")) throw new Error("unexpected authorization URL");
      window.location.assign(authorization_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the Gmail connection.");
      setConnecting(false);
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

  const header = (
    <PageHeader
      title="Email Accounts"
      description="Mailboxes your company sends from. Each email goes through the account you choose — never a shared system account."
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
      {header}
      {banner && (
        <Alert kind={banner.kind} onDismiss={() => router.replace("/email-accounts")}>
          {banner.text}
        </Alert>
      )}
      <Alert kind="success" onDismiss={success ? () => setSuccess("") : undefined}>
        {success}
      </Alert>
      <Alert kind="error" onDismiss={error ? () => setError("") : undefined}>
        {error}
      </Alert>

      <Card>
        <CardHeader
          icon="mail"
          title="Your accounts"
          meta={accounts.length ? `${accounts.length} total` : undefined}
          actions={
            <>
              <SubmitButton type="button" variant="secondary" size="sm" loading={connecting} onClick={connectGmail}>
                {!connecting && <Icon name="link" className="size-3.5" />} Connect Gmail (OAuth)
              </SubmitButton>
              <button type="button" className={buttonClass("primary", "sm")} onClick={startNew}>
                <Icon name="plus" className="size-3.5" /> Add SMTP account
              </button>
            </>
          }
        />
        {accounts.length === 0 ? (
          <EmptyState
            icon="mail"
            title="No email accounts configured"
            description="Connect an email account to start sending. Use SMTP (Gmail, Outlook or any provider) or connect Gmail with OAuth."
          />
        ) : (
          <div className="p-5">
            <div className="mb-4 max-w-md">
              <Field label="Test recipient" htmlFor="test_recipient" hint="Where Test sends its email. Defaults to the account's own address.">
                <input
                  id="test_recipient"
                  type="email"
                  placeholder="you@example.com"
                  value={testRecipient}
                  onChange={(e) => setTestRecipient(e.target.value)}
                />
              </Field>
            </div>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {accounts.map((a) => (
                <div
                  key={a.id}
                  className={cx(
                    "flex flex-col rounded-xl border p-4 transition",
                    a.is_default ? "border-blue-200 bg-blue-50/30" : "border-slate-200 bg-white",
                    !a.is_active && "opacity-75",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cx(
                        "grid size-10 shrink-0 place-items-center rounded-lg",
                        a.account_type === "OAUTH" ? "bg-teal-50 text-teal-600" : "bg-blue-50 text-blue-600",
                      )}
                    >
                      <Icon name={a.account_type === "OAUTH" ? "shield" : "server"} className="size-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-slate-900">{a.account_name}</p>
                      <p className="truncate text-sm text-slate-600">{a.email_address}</p>
                      <p className="truncate text-xs text-slate-500">
                        {providerLabel(a)} · sender “{a.sender_name}”
                      </p>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {a.is_default && <Badge tone="info">Default</Badge>}
                    <Badge tone={a.is_active ? "success" : "neutral"}>{a.is_active ? "Active" : "Inactive"}</Badge>
                    {a.account_type === "OAUTH" ? (
                      <Badge tone={a.oauth_connected ? "teal" : "danger"}>{a.oauth_connected ? "Connected" : "Not connected"}</Badge>
                    ) : (
                      <Badge tone={a.password_configured ? "teal" : "warning"}>
                        {a.password_configured ? "Password configured" : "No password"}
                      </Badge>
                    )}
                    {a.last_test_success === null ? (
                      <Badge>Not tested</Badge>
                    ) : a.last_test_success ? (
                      <Badge tone="success">Test passed</Badge>
                    ) : (
                      <Badge tone="danger">Test failed</Badge>
                    )}
                  </div>
                  {a.last_tested_at && <p className="mt-2 text-xs text-slate-500">Last test {new Date(a.last_tested_at).toLocaleString()}</p>}
                  {testResults[a.id] && (
                    <p className={cx("mt-2 text-xs font-medium", testResults[a.id].success ? "text-emerald-700" : "text-red-600")}>
                      {testResults[a.id].message}
                    </p>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                    <button className={buttonClass("secondary", "sm")} disabled={busy === a.id} onClick={() => runTest(a)}>
                      {busy === a.id ? <Spinner className="size-3" /> : <Icon name="send" className="size-3.5" />} Test
                    </button>
                    {!a.is_default && a.is_active && (
                      <button
                        className={buttonClass("secondary", "sm")}
                        disabled={busy === a.id}
                        onClick={() => act(a.id, () => api.setDefaultEmailAccount(a.id), `${a.account_name} is now the default account.`)}
                      >
                        <Icon name="star" className="size-3.5" /> Set default
                      </button>
                    )}
                    <button
                      className={buttonClass("secondary", "sm")}
                      disabled={busy === a.id}
                      onClick={() =>
                        act(a.id, () => api.updateEmailAccount(a.id, { is_active: !a.is_active }), a.is_active ? "Account deactivated." : "Account activated.")
                      }
                    >
                      <Icon name="power" className="size-3.5" /> {a.is_active ? "Deactivate" : "Activate"}
                    </button>
                    <button className={buttonClass("secondary", "sm")} onClick={() => startEdit(a)}>
                      <Icon name="edit" className="size-3.5" /> Edit
                    </button>
                    <button
                      className={buttonClass("ghost", "sm", "text-red-600 hover:bg-red-50 hover:text-red-700")}
                      disabled={busy === a.id}
                      aria-label={`Delete ${a.account_name}`}
                      onClick={() => {
                        if (window.confirm(`Delete ${a.account_name}? History keeps the sender address.`))
                          act(a.id, () => api.deleteEmailAccount(a.id), "Account deleted.");
                      }}
                    >
                      <Icon name="trash" className="size-3.5" /> Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {editing !== null && (
        <Card className="mt-5">
          <form onSubmit={onSave} noValidate autoComplete="off">
            <CardHeader
              icon={isNew ? "plus" : "edit"}
              title={isNew ? "Add SMTP account" : `Edit ${editing.account_name}`}
              description={isNew ? "Passwords are stored encrypted and never shown again." : undefined}
            />
            <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
              {isNew && (
                <Field label="Provider" htmlFor="provider" hint={PROVIDERS.find((p) => p.value === form.provider)?.hint} className="sm:col-span-2">
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
                  hint: isNew ? "Stored encrypted and never shown again. Gmail needs an App Password." : "Leave blank to keep the saved password.",
                })}
              {isNew && (
                <label className="flex items-center gap-2 text-sm font-medium text-slate-700 sm:col-span-2">
                  <input type="checkbox" checked={form.is_default} onChange={set("is_default")} />
                  Make this the default sending account
                </label>
              )}
            </div>
            <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-3.5">
              <button type="button" className={buttonClass("secondary")} onClick={() => setEditing(null)}>
                Cancel
              </button>
              <SubmitButton loading={saving}>{isNew ? "Add account" : "Save changes"}</SubmitButton>
            </div>
          </form>
        </Card>
      )}
    </>
  );
}
