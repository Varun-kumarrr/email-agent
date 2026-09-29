"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { Icon } from "@/components/Icon";
import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, Badge, buttonClass, Card, CardHeader, cx, Field, PageHeader, Spinner, StatusBadge, SubmitButton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { firstInvalidEmail, isEmail, parseEmailList } from "@/lib/emails";
import {
  FINAL_STATUSES,
  type Company,
  type EmailAccount,
  type EmailFormat,
  type EmailHistoryItem,
  type EmailTemplate,
  type GeneratedEmail,
  type SendEmailResult,
  type Tone,
} from "@/lib/types";

const TONES: { value: Tone; label: string }[] = [
  { value: "professional", label: "Professional" },
  { value: "friendly", label: "Friendly" },
  { value: "formal", label: "Formal" },
  { value: "persuasive", label: "Persuasive" },
  { value: "concise", label: "Concise" },
];

const PROVIDER_NAMES: Record<string, string> = { groq: "Groq", gemini: "Gemini", mock: "Mock" };
const providerName = (p: string) => PROVIDER_NAMES[p] ?? p;

// Safe, human-readable account label (never includes credentials, which the API never returns).
function accountLabel(a: EmailAccount): string {
  const kind =
    a.account_type === "OAUTH"
      ? `${a.provider === "GMAIL" ? "Gmail" : "Outlook"} (OAuth)`
      : a.provider === "GMAIL"
        ? "Gmail (SMTP)"
        : a.provider === "OUTLOOK"
          ? "Outlook (SMTP)"
          : "SMTP";
  return `${kind} — ${a.sender_name} <${a.email_address}>`;
}

// Compact option text for the narrow sender picker.
function accountOption(a: EmailAccount): string {
  const kind = a.account_type === "OAUTH" ? "OAuth" : a.provider === "GMAIL" ? "Gmail SMTP" : a.provider === "OUTLOOK" ? "Outlook SMTP" : "SMTP";
  return `${a.email_address} · ${kind}`;
}

interface RequestForm {
  recipient_name: string;
  recipient_email: string;
  purpose: string;
  tone: Tone;
  additional_instructions: string;
}

interface Draft {
  recipient: string;
  subject: string;
  body: string;
  format: EmailFormat;
  cc: string;
  bcc: string;
  appendSignature: boolean;
}

function ContextRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2 text-sm">
      <span className="shrink-0 text-slate-500">{label}</span>
      <span className="min-w-0 text-right font-medium break-words text-slate-800">{children}</span>
    </div>
  );
}

export default function AgentPage() {
  const [request, setRequest] = useState<RequestForm>({
    recipient_name: "",
    recipient_email: "",
    purpose: "",
    tone: "professional",
    additional_instructions: "",
  });
  const [requestErrors, setRequestErrors] = useState<Record<string, string>>({});
  const [generated, setGenerated] = useState<GeneratedEmail | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [draftErrors, setDraftErrors] = useState<Record<string, string>>({});
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [sendError, setSendError] = useState("");
  const [sent, setSent] = useState<SendEmailResult | null>(null);
  const [noCompany, setNoCompany] = useState(false);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [accounts, setAccounts] = useState<EmailAccount[] | null>(null); // null until loaded
  const [accountId, setAccountId] = useState(""); // "" = the company's default account
  const [company, setCompany] = useState<Company | null>(null);
  const [delivery, setDelivery] = useState<EmailHistoryItem | null>(null);
  const [pollCount, setPollCount] = useState(0);
  const [copied, setCopied] = useState(false);

  // Background delivery: poll the history record until it is SENT or FAILED (max ~2 minutes).
  const deliveryPending = !!sent && !FINAL_STATUSES.includes(delivery?.status ?? sent.status);
  useEffect(() => {
    if (!sent || !deliveryPending || pollCount > 60) return;
    const timer = window.setTimeout(async () => {
      try {
        setDelivery(await api.historyItem(sent.id));
      } catch {
        /* keep polling; a transient network error should not stop status updates */
      }
      setPollCount((n) => n + 1);
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [sent, deliveryPending, pollCount]);
  const [builtins, setBuiltins] = useState<string[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [templateVars, setTemplateVars] = useState<Record<string, string>>({});

  useEffect(() => {
    Promise.all([api.listTemplates(true), api.builtinTemplateVariables()])
      .then(([list, names]) => {
        setTemplates(list);
        setBuiltins(names);
        // "Use" on the Templates page links here with ?template=<id>.
        const requested = new URLSearchParams(window.location.search).get("template");
        const template = list.find((t) => t.id === requested);
        if (template) {
          setTemplateId(template.id);
          setTemplateVars(Object.fromEntries(template.variables.filter((v) => !names.includes(v)).map((v) => [v, ""])));
        }
      })
      .catch((err) => {
        if (isMissingCompany(err)) setNoCompany(true);
      });
    api
      .listEmailAccounts()
      .then(setAccounts)
      .catch((err) => {
        if (isMissingCompany(err)) setNoCompany(true);
        else setAccounts([]);
      });
    api
      .getCompany()
      .then(setCompany)
      .catch(() => setCompany(null));
  }, []);

  // Only active accounts can send. The backend re-checks ownership and status on every request.
  const activeAccounts = (accounts ?? []).filter((a) => a.is_active);
  const defaultAccount = activeAccounts.find((a) => a.is_default) ?? null;
  const noAccount = accounts !== null && activeAccounts.length === 0;
  const sendingAccount = activeAccounts.find((a) => a.id === accountId) ?? defaultAccount;

  const selectedTemplate = templates.find((t) => t.id === templateId) ?? null;

  function chooseTemplate(id: string) {
    setTemplateId(id);
    const template = templates.find((t) => t.id === id);
    // Ask only for the template's own variables; built-ins (company, sender, recipient) are filled automatically.
    setTemplateVars(Object.fromEntries((template?.variables ?? []).filter((v) => !builtins.includes(v)).map((v) => [v, ""])));
  }

  const setReq = (key: keyof RequestForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setRequest((r) => ({ ...r, [key]: e.target.value }));
  const setDraftField = (key: keyof Draft) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setDraft((d) => (d ? { ...d, [key]: e.target.value } : d));

  async function generate(event?: FormEvent) {
    event?.preventDefault();
    setError("");
    setSent(null);
    const errors: Record<string, string> = {};
    if (!request.recipient_name.trim()) errors.recipient_name = "Recipient name is required";
    if (!isEmail(request.recipient_email)) errors.recipient_email = "Enter a valid email address";
    if (!request.purpose.trim()) errors.purpose = "Describe what the email should achieve";
    setRequestErrors(errors);
    if (Object.keys(errors).length) return;

    setGenerating(true);
    try {
      const result = await api.generateEmail({
        recipient_name: request.recipient_name.trim(),
        recipient_email: request.recipient_email.trim(),
        purpose: request.purpose.trim(),
        tone: request.tone,
        additional_instructions: request.additional_instructions.trim() || null,
        email_account_id: accountId || null,
        template_id: templateId || null,
        template_variables: Object.fromEntries(Object.entries(templateVars).filter(([, v]) => v.trim())),
      });
      setGenerated(result);
      setDraft({
        recipient: result.recipient_email,
        subject: result.subject,
        body: result.body,
        format: result.suggested_format,
        cc: result.suggested_cc.join(", "),
        bcc: result.suggested_bcc.join(", "),
        appendSignature: result.signature_policy === "appended_on_send",
      });
      setDraftErrors({});
    } catch (err) {
      if (isMissingCompany(err)) setNoCompany(true);
      else if (err instanceof ApiError) {
        setRequestErrors(err.fieldErrors);
        setError(err.message);
      } else setError("Could not generate the email.");
    } finally {
      setGenerating(false);
    }
  }

  async function send() {
    if (!draft) return;
    setSendError("");
    setSent(null);
    if (!sendingAccount) {
      setSendError(
        noAccount ? "No email account configured. Add an email account before sending." : "Choose the email account to send from.",
      );
      return;
    }
    const errors: Record<string, string> = {};
    const cc = parseEmailList(draft.cc);
    const bcc = parseEmailList(draft.bcc);
    if (!isEmail(draft.recipient)) errors.recipient = "Enter a valid email address";
    if (!draft.subject.trim()) errors.subject = "Subject is required";
    else if (/[\r\n]/.test(draft.subject)) errors.subject = "Subject must be a single line";
    if (!draft.body.trim()) errors.body = "Body is required";
    const badCc = firstInvalidEmail(cc);
    if (badCc) errors.cc = `Invalid address: ${badCc}`;
    const badBcc = firstInvalidEmail(bcc);
    if (badBcc) errors.bcc = `Invalid address: ${badBcc}`;
    setDraftErrors(errors);
    if (Object.keys(errors).length) return;
    if (!window.confirm(`Send this email to ${draft.recipient} from ${sendingAccount.email_address}?`)) return;

    setSending(true);
    try {
      const result = await api.sendEmail({
        recipient: draft.recipient.trim(),
        subject: draft.subject.trim(),
        body: draft.body,
        format: draft.format,
        cc,
        bcc,
        append_signature: generated?.signature_preview ? draft.appendSignature : null,
        email_account_id: accountId || null,
      });
      setDelivery(null);
      setPollCount(0);
      setSent(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setDraftErrors(err.fieldErrors);
        const detail = err.status === 502 ? " The attempt was recorded in Email History." : "";
        setSendError(err.message + detail);
      } else setSendError("Could not send the email.");
    } finally {
      setSending(false);
    }
  }

  async function copyDraft() {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setSendError("Could not copy to the clipboard. Select the text and copy it manually.");
    }
  }

  const header = (
    <PageHeader
      title="AI Email Agent"
      description="Generate personalized emails from your company context, review and edit them, then send from your own account."
    />
  );

  if (noCompany) {
    return (
      <>
        {header}
        <NeedsCompany />
      </>
    );
  }

  const deliveryStatus = delivery?.status ?? sent?.status;

  return (
    <>
      {header}
      <Alert kind="error" onDismiss={error ? () => setError("") : undefined}>
        {error}
      </Alert>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="lg:self-start">
          <form onSubmit={generate} noValidate>
            <CardHeader icon="sparkles" title="Generate email" description="The agent writes only from your company profile — no invented facts." />
            <div className="space-y-4 p-5">
              {noAccount && (
                <Alert kind="warning">
                  No email account configured. Add an email account before sending. <Link href="/email-accounts">Go to Email Accounts</Link>
                </Alert>
              )}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Recipient name *" htmlFor="recipient_name" error={requestErrors.recipient_name}>
                  <input
                    id="recipient_name"
                    value={request.recipient_name}
                    onChange={setReq("recipient_name")}
                    placeholder="Priya Mehta"
                    className={requestErrors.recipient_name ? "invalid" : ""}
                  />
                </Field>
                <Field label="Recipient email *" htmlFor="recipient_email" error={requestErrors.recipient_email}>
                  <input
                    id="recipient_email"
                    type="email"
                    value={request.recipient_email}
                    onChange={setReq("recipient_email")}
                    placeholder="priya@example.com"
                    className={requestErrors.recipient_email ? "invalid" : ""}
                  />
                </Field>
              </div>
              <Field label="Email requirement *" htmlFor="purpose" error={requestErrors.purpose}>
                <textarea
                  id="purpose"
                  rows={4}
                  value={request.purpose}
                  onChange={setReq("purpose")}
                  placeholder="Write a professional follow-up email to a potential client who asked about our services last week…"
                  className={requestErrors.purpose ? "invalid" : ""}
                />
              </Field>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Tone" htmlFor="tone">
                  <select id="tone" value={request.tone} onChange={setReq("tone")}>
                    {TONES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Additional instructions" htmlFor="additional_instructions" error={requestErrors.additional_instructions}>
                  <input
                    id="additional_instructions"
                    value={request.additional_instructions}
                    onChange={setReq("additional_instructions")}
                    placeholder="Keep it under 150 words."
                  />
                </Field>
                <Field
                  label="Template (optional)"
                  htmlFor="template"
                  className="sm:col-span-2"
                  hint={
                    templates.length ? (
                      "The draft follows the template's structure and wording."
                    ) : (
                      <>
                        No active templates yet — <Link href="/templates">create one</Link>.
                      </>
                    )
                  }
                >
                  <select id="template" value={templateId} onChange={(e) => chooseTemplate(e.target.value)}>
                    <option value="">No template</option>
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                        {t.category ? ` (${t.category})` : ""}
                      </option>
                    ))}
                  </select>
                </Field>
                {selectedTemplate &&
                  Object.keys(templateVars).map((name) => (
                    <Field key={name} label={`Template: ${name}`} htmlFor={`tv-${name}`} error={requestErrors[`template_variables.${name}`]}>
                      <input
                        id={`tv-${name}`}
                        value={templateVars[name]}
                        onChange={(e) => setTemplateVars((v) => ({ ...v, [name]: e.target.value }))}
                        placeholder="Optional — the AI fills or removes empty ones"
                      />
                    </Field>
                  ))}
              </div>
            </div>
            <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-3.5">
              <p className="hidden text-xs text-slate-500 sm:block">Drafts are never sent automatically.</p>
              <SubmitButton loading={generating} className="ml-auto">
                {!generating && <Icon name="sparkles" className="size-4" />}
                {generating ? "Generating…" : generated ? "Generate again" : "Generate email"}
              </SubmitButton>
            </div>
          </form>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader
              icon="building"
              title="Company context"
              actions={
                <Link href="/company" className="text-xs font-semibold">
                  Edit
                </Link>
              }
            />
            <div className="divide-y divide-slate-100 px-5 py-1.5">
              {company ? (
                <>
                  <ContextRow label="Company">{company.name}</ContextRow>
                  {company.industry && <ContextRow label="Industry">{company.industry}</ContextRow>}
                  <ContextRow label="Services">{company.services.length}</ContextRow>
                  <ContextRow label="Target customers">{company.target_customers.length}</ContextRow>
                  <ContextRow label="Value propositions">{company.value_propositions.length}</ContextRow>
                </>
              ) : (
                <p className="py-2 text-sm text-slate-500">Loading company profile…</p>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader icon="mail" title="Sender account" />
            <div className="p-5">
              {activeAccounts.length > 0 ? (
                <>
                <Field label="Send from" htmlFor="email_account" hint="The draft is written for this sender and sent through this account.">
                  <select id="email_account" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                    {defaultAccount && <option value="">Default: {accountOption(defaultAccount)}</option>}
                    {!defaultAccount && <option value="">Choose an account…</option>}
                    {activeAccounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {accountOption(a)}
                        {a.is_default ? " (default)" : ""}
                      </option>
                    ))}
                  </select>
                </Field>
                {sendingAccount && (
                  <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs">
                    <p className="font-semibold break-all text-slate-800">{sendingAccount.sender_name}</p>
                    <p className="break-all text-slate-500">{accountLabel(sendingAccount)}</p>
                  </div>
                )}
                </>
              ) : (
                <p className="text-sm text-slate-500">
                  {accounts === null ? (
                    "Loading accounts…"
                  ) : (
                    <>
                      No active email account. <Link href="/email-accounts">Add one</Link>.
                    </>
                  )}
                </p>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader icon="bot" title="AI provider" />
            <div className="p-5 text-sm">
              {generated ? (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-slate-900">{providerName(generated.provider)}</span>
                    {generated.fallback_used ? (
                      <Badge tone="warning">
                        {generated.provider === "mock" ? "Mock fallback used" : `${providerName(generated.provider)} fallback used`}
                      </Badge>
                    ) : (
                      <Badge tone="success">
                        <span className="size-1.5 rounded-full bg-emerald-500" /> Generated successfully
                      </Badge>
                    )}
                  </div>
                  {generated.warning && <p className="text-xs text-amber-700">{generated.warning}</p>}
                </div>
              ) : (
                <p className="text-slate-500">
                  The provider that writes the draft — Groq, with Gemini and a template-based mock as fallbacks — appears here after
                  generation.
                </p>
              )}
            </div>
          </Card>
        </div>
      </div>

      {generating && (
        <Card className="mt-5">
          <div className="flex items-center gap-3 p-5" role="status">
            <Spinner className="size-5 text-blue-600" />
            <div>
              <p className="text-sm font-semibold text-slate-800">Generating your email…</p>
              <p className="text-xs text-slate-500">Using your company profile, sender identity and signature settings.</p>
            </div>
          </div>
          <div className="space-y-2.5 px-5 pb-5" aria-hidden="true">
            <div className="h-3 w-2/3 animate-pulse rounded bg-slate-100" />
            <div className="h-3 w-full animate-pulse rounded bg-slate-100" />
            <div className="h-3 w-5/6 animate-pulse rounded bg-slate-100" />
          </div>
        </Card>
      )}

      {draft && generated && (
        <Card className="mt-5">
          <CardHeader
            icon="edit"
            title="Generated email"
            description="Every field is editable. Check each fact before sending — AI can make mistakes."
            actions={
              <>
                <button type="button" className={buttonClass("secondary", "sm")} onClick={copyDraft}>
                  <Icon name={copied ? "check" : "copy"} className="size-3.5" /> {copied ? "Copied" : "Copy"}
                </button>
                <SubmitButton type="button" variant="secondary" size="sm" loading={generating} onClick={() => generate()}>
                  {!generating && <Icon name="refresh" className="size-3.5" />} Regenerate
                </SubmitButton>
              </>
            }
          />
          <div className="space-y-4 p-5">
            {generated.warning && <Alert kind="warning">{generated.warning}</Alert>}
            {generated.missing_template_variables.length > 0 && (
              <Alert kind="info">No value was given for: {generated.missing_template_variables.join(", ")}. Check the draft before sending.</Alert>
            )}

            <div className="overflow-hidden rounded-xl border border-slate-200">
              <div className="grid grid-cols-1 gap-3 border-b border-slate-100 bg-slate-50/70 p-4 sm:grid-cols-2">
                <Field label="From" htmlFor="draft_from">
                  <input
                    id="draft_from"
                    value={sendingAccount ? accountLabel(sendingAccount) : noAccount ? "No email account configured" : "Choose an account under Sender account"}
                    disabled
                  />
                </Field>
                <Field label="To" htmlFor="draft_recipient" error={draftErrors.recipient}>
                  <input id="draft_recipient" type="email" value={draft.recipient} onChange={setDraftField("recipient")} className={draftErrors.recipient ? "invalid" : ""} />
                </Field>
                <Field label="CC" htmlFor="draft_cc" error={draftErrors.cc} hint="Comma-separated">
                  <input id="draft_cc" value={draft.cc} onChange={setDraftField("cc")} className={draftErrors.cc ? "invalid" : ""} />
                </Field>
                <Field label="BCC" htmlFor="draft_bcc" error={draftErrors.bcc} hint="Hidden from other recipients">
                  <input id="draft_bcc" value={draft.bcc} onChange={setDraftField("bcc")} className={draftErrors.bcc ? "invalid" : ""} />
                </Field>
              </div>
              <div className="space-y-4 p-4">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_180px]">
                  <Field label="Subject" htmlFor="draft_subject" error={draftErrors.subject}>
                    <input id="draft_subject" value={draft.subject} onChange={setDraftField("subject")} className={cx("font-medium", draftErrors.subject && "invalid")} />
                  </Field>
                  <Field label="Format" htmlFor="draft_format">
                    <select id="draft_format" value={draft.format} onChange={setDraftField("format")}>
                      <option value="PLAIN_TEXT">Plain text</option>
                      <option value="HTML">HTML</option>
                    </select>
                  </Field>
                </div>
                <Field label="Body" htmlFor="draft_body" error={draftErrors.body}>
                  <textarea id="draft_body" rows={14} value={draft.body} onChange={setDraftField("body")} className={draftErrors.body ? "invalid" : ""} />
                </Field>

                {generated.signature_preview && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
                    <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                      <input type="checkbox" checked={draft.appendSignature} onChange={(e) => setDraft({ ...draft, appendSignature: e.target.checked })} />
                      Append my signature when sending
                    </label>
                    {draft.appendSignature && (
                      <pre className="mt-2 font-sans text-sm whitespace-pre-wrap text-slate-600">{generated.signature_preview}</pre>
                    )}
                  </div>
                )}
              </div>
            </div>

            {sendError && <Alert kind="error">{sendError}</Alert>}
            {sent && (
              <Alert kind={deliveryStatus === "FAILED" ? "error" : "success"}>
                <span className="mr-1.5 inline-block align-middle">
                  <StatusBadge status={deliveryStatus ?? sent.status} />
                </span>
                {deliveryStatus === "SENT" && sent.status !== "SENT"
                  ? `Email sent to ${sent.recipient}.`
                  : deliveryStatus === "FAILED"
                    ? `Delivery failed: ${delivery?.error_message ?? "see Email History."}`
                    : sent.message}{" "}
                From {sent.sender_name ? `${sent.sender_name} <${sent.sender_email}>` : sent.sender_email}
                {sent.signature_appended ? " · signature appended" : ""}. {deliveryPending && "Checking delivery status… "}
                <Link href="/history">View history</Link>
              </Alert>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-3.5">
            <p className="text-xs text-slate-500">
              Sending from <span className="font-semibold text-slate-700">{sendingAccount ? sendingAccount.email_address : "no account"}</span>
            </p>
            <SubmitButton type="button" loading={sending} onClick={send} disabled={!sendingAccount}>
              {!sending && <Icon name="send" className="size-4" />} Send email
            </SubmitButton>
          </div>
        </Card>
      )}
    </>
  );
}
