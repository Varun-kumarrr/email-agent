"use client";

import { useEffect, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, Field, LoadingScreen, PageHeader, SubmitButton } from "@/components/ui";
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

  if (loading) return <LoadingScreen />;
  if (noCompany) {
    return (
      <>
        <PageHeader title="Email Signature" />
        <NeedsCompany />
      </>
    );
  }

  let behaviour = "The signature is disabled and will not be used.";
  if (enabled && appendAutomatically) behaviour = "Appended automatically to every email you send.";
  else if (enabled) behaviour = "Added to AI drafts so you can edit it; not appended automatically.";

  return (
    <>
      <PageHeader title="Email Signature" description="A reusable signature for AI drafts and outgoing emails." />
      <Alert kind="success">{success}</Alert>
      <Alert kind="error">{error}</Alert>

      <div className="grid grid-2">
        <form className="card" onSubmit={onSubmit} noValidate>
          <h2>Edit signature</h2>
          <div className="stack">
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
              <button type="button" className="btn btn-secondary btn-small" onClick={() => setText(EXAMPLE)} style={{ alignSelf: "flex-start" }}>
                Use example
              </button>
            )}
            <label className="checkbox">
              <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
              Enabled
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={appendAutomatically}
                disabled={!enabled}
                onChange={(e) => setAppendAutomatically(e.target.checked)}
              />
              Append automatically to outgoing emails
            </label>
          </div>
          <div className="form-actions">
            <SubmitButton loading={saving}>{exists ? "Save changes" : "Create signature"}</SubmitButton>
            {exists && (
              <SubmitButton type="button" className="btn btn-danger" loading={deleting} onClick={onDelete}>
                Delete
              </SubmitButton>
            )}
          </div>
        </form>

        <div className="card">
          <h2>Preview</h2>
          <div className="preview">
            <span className="muted">Hi Priya,{"\n\n"}…your email body…{"\n\n"}</span>
            {enabled && text ? text : <span className="muted">(no signature)</span>}
          </div>
          <p className="muted" style={{ marginBottom: 0 }}>{behaviour}</p>
        </div>
      </div>
    </>
  );
}
