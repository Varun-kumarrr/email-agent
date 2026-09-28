"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, Field, PageHeader, StatusBadge, SubmitButton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { firstInvalidEmail, isEmail, parseEmailList } from "@/lib/emails";
import {
  FINAL_STATUSES,
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
  const [delivery, setDelivery] = useState<EmailHistoryItem | null>(null);
  const [pollCount, setPollCount] = useState(0);

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

  if (noCompany) {
    return (
      <>
        <PageHeader title="AI Email Agent" />
        <NeedsCompany />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="AI Email Agent"
        description="Describe the email you need. The agent writes it from your company profile; you review and edit before sending."
      />
      <Alert kind="error">{error}</Alert>

      <form className="card" onSubmit={generate} noValidate>
        <h2>1. What should the email say?</h2>
        {noAccount && (
          <Alert kind="warning">
            No email account configured. Add an email account before sending.{" "}
            <Link href="/email-accounts">Go to Email Accounts</Link>
          </Alert>
        )}
        <div className="grid grid-2">
          {activeAccounts.length > 0 && (
            <Field
              label="Send from"
              htmlFor="email_account"
              className="span-2"
              hint="The draft is written for this sender, and the email is sent through this account."
            >
              <select id="email_account" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                {defaultAccount && <option value="">Default account: {accountLabel(defaultAccount)}</option>}
                {!defaultAccount && <option value="">Choose an account…</option>}
                {activeAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {accountLabel(a)}
                    {a.is_default ? " (default)" : ""}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label="Recipient name *" htmlFor="recipient_name" error={requestErrors.recipient_name}>
            <input id="recipient_name" value={request.recipient_name} onChange={setReq("recipient_name")} placeholder="Priya Mehta" className={requestErrors.recipient_name ? "invalid" : ""} />
          </Field>
          <Field label="Recipient email *" htmlFor="recipient_email" error={requestErrors.recipient_email}>
            <input id="recipient_email" type="email" value={request.recipient_email} onChange={setReq("recipient_email")} placeholder="priya@smallbiz.in" className={requestErrors.recipient_email ? "invalid" : ""} />
          </Field>
          <Field label="Purpose / requirement *" htmlFor="purpose" error={requestErrors.purpose} className="span-2">
            <textarea
              id="purpose"
              rows={3}
              value={request.purpose}
              onChange={setReq("purpose")}
              placeholder="Write a professional cold email introducing our CRM to a small business owner."
              className={requestErrors.purpose ? "invalid" : ""}
            />
          </Field>
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
            <input id="additional_instructions" value={request.additional_instructions} onChange={setReq("additional_instructions")} placeholder="Keep it under 150 words." />
          </Field>
          <Field
            label="Template (optional)"
            htmlFor="template"
            hint={templates.length ? "The draft follows the template's structure and wording." : "No active templates yet — create one on the Templates page."}
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
        <div className="form-actions">
          <SubmitButton loading={generating}>{generated ? "Generate Again" : "Generate Email"}</SubmitButton>
        </div>
      </form>

      {generating && !draft && <Alert kind="info">Writing your email…</Alert>}

      {draft && generated && (
        <div className="card">
          <h2>2. Review and edit</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            Generated by <span className="badge badge-info">{generated.provider}</span>. Check every fact before sending — AI can make mistakes.
          </p>
          <p className="muted">
            Sending from: <strong>{sendingAccount ? accountLabel(sendingAccount) : noAccount ? "no email account configured" : "choose an account above"}</strong>
          </p>
          {generated.warning && <Alert kind="warning">{generated.warning}</Alert>}
          {generated.missing_template_variables.length > 0 && (
            <Alert kind="info">
              No value was given for: {generated.missing_template_variables.join(", ")}. Check the draft before sending.
            </Alert>
          )}

          <div className="stack">
            <div className="grid grid-2">
              <Field label="To" htmlFor="draft_recipient" error={draftErrors.recipient}>
                <input id="draft_recipient" type="email" value={draft.recipient} onChange={setDraftField("recipient")} className={draftErrors.recipient ? "invalid" : ""} />
              </Field>
              <Field label="Format" htmlFor="draft_format">
                <select id="draft_format" value={draft.format} onChange={setDraftField("format")}>
                  <option value="PLAIN_TEXT">Plain text</option>
                  <option value="HTML">HTML</option>
                </select>
              </Field>
              <Field label="CC" htmlFor="draft_cc" error={draftErrors.cc} hint="Comma-separated">
                <input id="draft_cc" value={draft.cc} onChange={setDraftField("cc")} className={draftErrors.cc ? "invalid" : ""} />
              </Field>
              <Field label="BCC" htmlFor="draft_bcc" error={draftErrors.bcc} hint="Comma-separated; hidden from other recipients">
                <input id="draft_bcc" value={draft.bcc} onChange={setDraftField("bcc")} className={draftErrors.bcc ? "invalid" : ""} />
              </Field>
            </div>
            <Field label="Subject" htmlFor="draft_subject" error={draftErrors.subject}>
              <input id="draft_subject" value={draft.subject} onChange={setDraftField("subject")} className={draftErrors.subject ? "invalid" : ""} />
            </Field>
            <Field label="Body" htmlFor="draft_body" error={draftErrors.body}>
              <textarea id="draft_body" rows={14} value={draft.body} onChange={setDraftField("body")} className={draftErrors.body ? "invalid" : ""} />
            </Field>

            {generated.signature_preview && (
              <div>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={draft.appendSignature}
                    onChange={(e) => setDraft({ ...draft, appendSignature: e.target.checked })}
                  />
                  Append my signature when sending
                </label>
                {draft.appendSignature && <div className="preview" style={{ marginTop: 8 }}>{generated.signature_preview}</div>}
              </div>
            )}
          </div>

          <div className="form-actions">
            <SubmitButton type="button" className="btn btn-secondary" loading={generating} onClick={() => generate()}>
              Generate Again
            </SubmitButton>
            <SubmitButton type="button" loading={sending} onClick={send} disabled={!sendingAccount}>
              Send Email
            </SubmitButton>
          </div>
          {sendError && (
            <div style={{ marginTop: 14 }}>
              <Alert kind="error">{sendError}</Alert>
            </div>
          )}
          {sent && (
            <div style={{ marginTop: 14 }}>
              <Alert kind={(delivery?.status ?? sent.status) === "FAILED" ? "error" : "success"}>
                <StatusBadge status={delivery?.status ?? sent.status} />{" "}
                {(delivery?.status ?? sent.status) === "SENT" && sent.status !== "SENT"
                  ? `Email sent to ${sent.recipient}.`
                  : (delivery?.status ?? sent.status) === "FAILED"
                    ? `Delivery failed: ${delivery?.error_message ?? "see Email History."}`
                    : sent.message}{" "}
                From {sent.sender_name ? `${sent.sender_name} <${sent.sender_email}>` : sent.sender_email}
                {sent.signature_appended ? " · signature appended" : ""}.{" "}
                {deliveryPending && "Checking delivery status… "}
                <Link href="/history">View history</Link>
              </Alert>
            </div>
          )}
        </div>
      )}
    </>
  );
}
