"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, Field, LoadingScreen, PageHeader, SubmitButton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { firstInvalidEmail, isEmail, parseEmailList } from "@/lib/emails";
import type { EmailFormat, Preferences, PreferencesInput, Signature } from "@/lib/types";

interface FormState {
  sender_name: string;
  reply_to: string;
  default_format: EmailFormat;
  daily_send_limit: string;
  max_recipients_per_email: string;
  max_send_retries: string;
  default_cc: string;
  default_bcc: string;
}

function fromPreferences(p: Preferences): FormState {
  return {
    sender_name: p.sender_name ?? "",
    reply_to: p.reply_to ?? "",
    default_format: p.default_format,
    daily_send_limit: String(p.daily_send_limit),
    max_recipients_per_email: String(p.max_recipients_per_email),
    max_send_retries: String(p.max_send_retries),
    default_cc: p.default_cc.join(", "),
    default_bcc: p.default_bcc.join(", "),
  };
}

function intInRange(value: string, min: number, max: number) {
  const n = Number(value);
  return Number.isInteger(n) && n >= min && n <= max;
}

function validate(f: FormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (f.reply_to.trim() && !isEmail(f.reply_to)) errors.reply_to = "Enter a valid email address";
  if (!intInRange(f.daily_send_limit, 1, 10000)) errors.daily_send_limit = "Between 1 and 10000";
  if (!intInRange(f.max_recipients_per_email, 1, 50)) errors.max_recipients_per_email = "Between 1 and 50";
  if (!intInRange(f.max_send_retries, 0, 5)) errors.max_send_retries = "Between 0 and 5";
  const badCc = firstInvalidEmail(parseEmailList(f.default_cc));
  if (badCc) errors.default_cc = `Invalid address: ${badCc}`;
  const badBcc = firstInvalidEmail(parseEmailList(f.default_bcc));
  if (badBcc) errors.default_bcc = `Invalid address: ${badBcc}`;
  return errors;
}

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [signature, setSignature] = useState<Signature | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [noCompany, setNoCompany] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    Promise.all([api.getPreferences(), api.getSignature().catch(() => null)])
      .then(([p, s]) => {
        setPrefs(p);
        setForm(fromPreferences(p));
        setSignature(s);
      })
      .catch((err) => {
        if (isMissingCompany(err)) setNoCompany(true);
        else setError(err instanceof ApiError ? err.message : "Could not load preferences.");
      })
      .finally(() => setLoading(false));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!form || !prefs) return;
    setError("");
    setSuccess("");
    const clientErrors = validate(form);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    const payload: PreferencesInput = {
      sender_name: form.sender_name.trim() || null,
      reply_to: form.reply_to.trim() || null,
      default_format: form.default_format,
      daily_send_limit: Number(form.daily_send_limit),
      max_recipients_per_email: Number(form.max_recipients_per_email),
      max_send_retries: Number(form.max_send_retries),
      default_cc: parseEmailList(form.default_cc),
      default_bcc: parseEmailList(form.default_bcc),
      extra_settings: prefs.extra_settings, // preserved as-is
    };

    setSaving(true);
    try {
      if (signature) {
        // Default-signature settings live on the signature itself.
        setSignature(
          await api.updateSignature({
            signature_text: signature.signature_text,
            enabled: signature.enabled,
            append_automatically: signature.append_automatically,
          }),
        );
      }
      const saved = await api.updatePreferences(payload);
      setPrefs(saved);
      setForm(fromPreferences(saved));
      setSuccess("Preferences saved.");
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setError(err.message);
      } else {
        setError("Could not save preferences.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingScreen />;
  if (noCompany) {
    return (
      <>
        <PageHeader title="Email Preferences" />
        <NeedsCompany />
      </>
    );
  }
  if (!form || !prefs) return <Alert kind="error">{error || "Could not load preferences."}</Alert>;

  const set = (key: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => (f ? { ...f, [key]: e.target.value } : f));

  const input = (key: keyof FormState, label: string, opts: { type?: string; hint?: string; placeholder?: string } = {}) => (
    <Field label={label} htmlFor={key} error={errors[key]} hint={opts.hint}>
      <input
        id={key}
        type={opts.type ?? "text"}
        value={form[key]}
        placeholder={opts.placeholder}
        onChange={set(key)}
        className={errors[key] ? "invalid" : ""}
      />
    </Field>
  );

  return (
    <>
      <PageHeader title="Email Preferences" description="Defaults applied when generating and sending emails." />
      <Alert kind="success">{success}</Alert>
      <Alert kind="error">{error}</Alert>

      <div className="card">
        <div className="grid grid-3">
          <div>
            <div className="muted">Sender used</div>
            <strong>{prefs.effective_sender_name || "—"}</strong>
          </div>
          <div>
            <div className="muted">Reply-to used</div>
            <strong>{prefs.effective_reply_to || "—"}</strong>
          </div>
          <div>
            <div className="muted">Sent today</div>
            <strong>
              {prefs.sent_today} / {prefs.daily_send_limit}
            </strong>{" "}
            <span className="muted">({prefs.remaining_today} left)</span>
          </div>
        </div>
      </div>

      <form onSubmit={onSubmit} noValidate>
        <div className="card">
          <h2>Sender</h2>
          <div className="grid grid-2">
            {input("sender_name", "Sender name", { hint: "Leave blank to use the name from Email Configuration." })}
            {input("reply_to", "Reply-to email", { type: "email", hint: "Leave blank to use the Email Configuration value." })}
          </div>
        </div>

        <div className="card">
          <h2>Signature</h2>
          {signature ? (
            <div className="stack">
              <div className="preview">{signature.signature_text}</div>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={signature.enabled}
                  onChange={(e) => setSignature({ ...signature, enabled: e.target.checked })}
                />
                Use this as the default signature
              </label>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={signature.append_automatically}
                  disabled={!signature.enabled}
                  onChange={(e) => setSignature({ ...signature, append_automatically: e.target.checked })}
                />
                Automatically append the signature to outgoing emails
              </label>
              <Link href="/signature">Edit signature text</Link>
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              No signature yet. <Link href="/signature">Create one</Link> to use it as your default.
            </p>
          )}
        </div>

        <div className="card">
          <h2>Format & recipients</h2>
          <div className="grid grid-2">
            <Field label="Default email format" htmlFor="default_format">
              <select id="default_format" value={form.default_format} onChange={set("default_format")}>
                <option value="PLAIN_TEXT">Plain text</option>
                <option value="HTML">HTML</option>
              </select>
            </Field>
            <div />
            <Field label="Default CC" htmlFor="default_cc" error={errors.default_cc} hint="Comma-separated addresses.">
              <textarea id="default_cc" rows={2} value={form.default_cc} onChange={set("default_cc")} className={errors.default_cc ? "invalid" : ""} />
            </Field>
            <Field label="Default BCC" htmlFor="default_bcc" error={errors.default_bcc} hint="Comma-separated addresses.">
              <textarea id="default_bcc" rows={2} value={form.default_bcc} onChange={set("default_bcc")} className={errors.default_bcc ? "invalid" : ""} />
            </Field>
          </div>
        </div>

        <div className="card">
          <h2>Sending limits</h2>
          <div className="grid grid-3">
            {input("daily_send_limit", "Daily send limit", { type: "number", hint: "Emails per day (UTC)." })}
            {input("max_recipients_per_email", "Max recipients per email", { type: "number", hint: "To + CC + BCC." })}
            {input("max_send_retries", "Retries on temporary errors", { type: "number", hint: "0–5 automatic retries." })}
          </div>
        </div>

        <div className="form-actions">
          <SubmitButton loading={saving}>Save preferences</SubmitButton>
        </div>
      </form>
    </>
  );
}
