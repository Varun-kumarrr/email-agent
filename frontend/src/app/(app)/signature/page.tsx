"use client";

import { useEffect, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, buttonClass, Card, CardHeader, Field, LoadingScreen, PageHeader, SubmitButton, Switch } from "@/components/ui";
import { api, ApiError, isNotFound } from "@/lib/api";

const EXAMPLE = `Best Regards,
Anjali
Business Development Manager
ABC Technologies
Email: anjali@abctech.com
Phone: +91 XXXXX XXXXX
Website: www.abctech.com`;

export default function SignaturePage() {
  const [text, setText] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [appendAutomatically, setAppendAutomatically] = useState(true);
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [noCompany, setNoCompany] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [fieldError, setFieldError] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    api
      .getSignature()
      .then((s) => {
        setText(s.signature_text);
        setEnabled(s.enabled);
        setAppendAutomatically(s.append_automatically);
        setExists(true);
      })
      .catch((err) => {
        if (isMissingCompany(err)) setNoCompany(true);
        else if (!isNotFound(err)) setError(err instanceof ApiError ? err.message : "Could not load the signature.");
      })
      .finally(() => setLoading(false));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setFieldError("");
    if (!text.trim()) {
      setFieldError("Signature text is required");
      return;
    }
    if (text.length > 2000) {
      setFieldError("Keep the signature under 2000 characters");
      return;
    }
    setSaving(true);
    const payload = { signature_text: text, enabled, append_automatically: appendAutomatically };
    try {
      const saved = exists ? await api.updateSignature(payload) : await api.createSignature(payload);
      setText(saved.signature_text);
      setExists(true);
      setSuccess("Signature saved.");
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldError(err.fieldErrors.signature_text ?? "");
        setError(err.message);
      } else {
        setError("Could not save the signature.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function onDelete() {
    if (!window.confirm("Delete your email signature?")) return;
    setDeleting(true);
    setError("");
    setSuccess("");
    try {
      await api.deleteSignature();
      setExists(false);
      setText("");
      setEnabled(true);
      setAppendAutomatically(true);
      setSuccess("Signature deleted.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the signature.");
    } finally {
      setDeleting(false);
    }
  }

  const header = <PageHeader title="Email Signature" description="A reusable signature for AI drafts and outgoing emails." />;

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

  let behaviour = "The signature is disabled and will not be used.";
  if (enabled && appendAutomatically) behaviour = "Appended automatically to every email you send.";
  else if (enabled) behaviour = "Added to AI drafts so you can edit it; not appended automatically.";

  return (
    <>
      {header}
      <Alert kind="success" onDismiss={success ? () => setSuccess("") : undefined}>
        {success}
      </Alert>
      <Alert kind="error" onDismiss={error ? () => setError("") : undefined}>
        {error}
      </Alert>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <form onSubmit={onSubmit} noValidate>
            <CardHeader icon="pen" title="Email signature" meta={exists ? undefined : "Not created yet"} />
            <div className="space-y-4 p-5">
              <Field label="Signature text" htmlFor="signature_text" error={fieldError} hint={`${text.length}/2000 characters`}>
                <textarea
                  id="signature_text"
                  rows={9}
                  value={text}
                  placeholder={EXAMPLE}
                  onChange={(e) => setText(e.target.value)}
                  className={fieldError ? "invalid" : ""}
                />
              </Field>
              {!text && (
                <button type="button" className={buttonClass("secondary", "sm")} onClick={() => setText(EXAMPLE)}>
                  Use example
                </button>
              )}
              <div className="space-y-3 rounded-lg border border-slate-200 p-3.5">
                <Switch label="Enabled" description="Use this signature for drafts and emails." checked={enabled} onChange={setEnabled} />
                <Switch
                  label="Append automatically"
                  description="Added once to every outgoing email."
                  checked={appendAutomatically}
                  disabled={!enabled}
                  onChange={setAppendAutomatically}
                />
              </div>
            </div>
            <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-3.5">
              {exists && (
                <SubmitButton type="button" variant="secondary" className="text-red-600! hover:bg-red-50! hover:text-red-700!" loading={deleting} onClick={onDelete}>
                  Delete
                </SubmitButton>
              )}
              <SubmitButton loading={saving}>{exists ? "Save signature" : "Create signature"}</SubmitButton>
            </div>
          </form>
        </Card>

        <Card>
          <CardHeader icon="eye" title="Preview" description={behaviour} />
          <div className="p-5">
            <div className="overflow-hidden rounded-xl border border-slate-200">
              <div className="space-y-1 border-b border-slate-100 bg-slate-50/70 px-4 py-3 text-xs text-slate-500">
                <p>
                  <span className="inline-block w-14 font-semibold text-slate-600">To</span> recipient@example.com
                </p>
                <p>
                  <span className="inline-block w-14 font-semibold text-slate-600">Subject</span> Your email subject
                </p>
              </div>
              <div className="px-4 py-4 text-sm leading-relaxed">
                <p className="text-slate-400">Hi Priya,</p>
                <p className="mt-3 text-slate-400">…your email body…</p>
                <div className="mt-4 border-t border-dashed border-slate-200 pt-3">
                  {enabled && text ? (
                    <pre className="font-sans whitespace-pre-wrap text-slate-800">{text}</pre>
                  ) : (
                    <p className="text-slate-400 italic">(no signature)</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
