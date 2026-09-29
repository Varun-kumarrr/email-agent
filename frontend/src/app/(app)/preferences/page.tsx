"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, Card, CardHeader, cx, Field, LoadingScreen, PageHeader, SubmitButton, Switch } from "@/components/ui";
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

  const header = <PageHeader title="Email Preferences" description="Defaults applied when generating and sending emails." />;

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
  if (!form || !prefs)
    return (
      <>
        {header}
        <Alert kind="error">{error || "Could not load preferences."}</Alert>
      </>
    );

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

  const summary = [
    { label: "Sender used", value: prefs.effective_sender_name || "—" },
    { label: "Reply-to used", value: prefs.effective_reply_to || "—" },
    { label: "Sent today", value: `${prefs.sent_today} / ${prefs.daily_send_limit}`, note: `${prefs.remaining_today} left` },
  ];

  return (
    <>
      {header}
      <Alert kind="success" onDismiss={success ? () => setSuccess("") : undefined}>
        {success}
      </Alert>
      <Alert kind="error" onDismiss={error ? () => setError("") : undefined}>
        {error}
      </Alert>

      <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {summary.map((item) => (
          <div key={item.label} className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
            <p className="text-[11px] font-semibold tracking-wider text-slate-500 uppercase">{item.label}</p>
            <p className="mt-1 truncate font-semibold text-slate-900">
              {item.value} {item.note && <span className="text-xs font-medium text-blue-600">· {item.note}</span>}
            </p>
          </div>
        ))}
      </div>

      <form onSubmit={onSubmit} noValidate>
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader icon="user" title="Sender settings" description="Override the sending account's name and reply-to." />
            <div className="space-y-4 p-5">
              {input("sender_name", "Sender name", { hint: "Leave blank to use the sending email account's sender name." })}
              {input("reply_to", "Reply-to email", { type: "email", hint: "Leave blank to use the sending email account's reply-to." })}
            </div>
          </Card>

          <Card>
            <CardHeader
              icon="pen"
              title="Default signature"
              actions={
                <Link href="/signature" className="text-xs font-semibold">
                  {signature ? "Edit signature" : "Create one"}
                </Link>
              }
            />
            <div className="space-y-4 p-5">
              {signature ? (
                <>
                  <pre className="max-h-32 overflow-auto rounded-lg bg-slate-50 px-3 py-2 font-sans text-xs whitespace-pre-wrap text-slate-600">
                    {signature.signature_text}
                  </pre>
                  <Switch
                    label="Use as the default signature"
                    checked={signature.enabled}
                    onChange={(value) => setSignature({ ...signature, enabled: value })}
                  />
                  <Switch
                    label="Auto-append to outgoing emails"
                    description="Added once when sending, never duplicated."
                    checked={signature.append_automatically}
                    disabled={!signature.enabled}
                    onChange={(value) => setSignature({ ...signature, append_automatically: value })}
                  />
                </>
              ) : (
                <p className="text-sm text-slate-500">
                  No signature yet. <Link href="/signature">Create one</Link> to use it as your default.
                </p>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader icon="mail" title="Email format & CC / BCC" />
            <div className="space-y-4 p-5">
              <fieldset>
                <legend className="mb-1.5 text-xs font-semibold text-slate-700">Default email format</legend>
                <div className="inline-flex rounded-lg border border-slate-300 bg-slate-50 p-0.5" role="radiogroup">
                  {(["PLAIN_TEXT", "HTML"] as EmailFormat[]).map((fmt) => (
                    <label
                      key={fmt}
                      className={cx(
                        "cursor-pointer rounded-md px-3.5 py-1.5 text-sm font-medium transition has-focus-visible:outline-2 has-focus-visible:outline-blue-500",
                        form.default_format === fmt ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800",
                      )}
                    >
                      <input
                        type="radio"
                        name="default_format"
                        value={fmt}
                        checked={form.default_format === fmt}
                        onChange={set("default_format")}
                        className="sr-only"
                      />
                      {fmt === "HTML" ? "HTML" : "Plain text"}
                    </label>
                  ))}
                </div>
              </fieldset>
              <Field label="Default CC" htmlFor="default_cc" error={errors.default_cc} hint="Comma-separated addresses.">
                <textarea id="default_cc" rows={2} value={form.default_cc} onChange={set("default_cc")} className={cx("min-h-0", errors.default_cc && "invalid")} />
              </Field>
              <Field label="Default BCC" htmlFor="default_bcc" error={errors.default_bcc} hint="Comma-separated addresses.">
                <textarea id="default_bcc" rows={2} value={form.default_bcc} onChange={set("default_bcc")} className={cx("min-h-0", errors.default_bcc && "invalid")} />
              </Field>
            </div>
          </Card>

          <Card>
            <CardHeader icon="gauge" title="Sending limits" description="Protects your mailbox reputation." />
            <div className="space-y-4 p-5">
              {input("daily_send_limit", "Daily send limit", { type: "number", hint: "Emails per day (UTC). Test emails don't count." })}
              {input("max_recipients_per_email", "Max recipients per email", { type: "number", hint: "To + CC + BCC." })}
              {input("max_send_retries", "Retries on temporary errors", { type: "number", hint: "0–5 automatic retries." })}
            </div>
          </Card>
        </div>

        <div className="sticky bottom-0 z-10 mt-5 -mx-4 flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border sm:bg-white/95 sm:shadow-sm">
          <SubmitButton loading={saving}>Save preferences</SubmitButton>
        </div>
      </form>
    </>
  );
}
