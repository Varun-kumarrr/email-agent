"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, Field, LoadingScreen, PageHeader, SubmitButton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { EmailFormat, EmailTemplate, EmailTemplateInput, TemplatePreview } from "@/lib/types";

const PLACEHOLDER = /\{\{\s*([A-Za-z_][A-Za-z0-9_]{0,63})\s*\}\}/g;

const EMPTY: EmailTemplateInput = {
  name: "",
  description: null,
  category: null,
  subject_template: "{{company_name}}: {{product_name}} for your team",
  body_template:
    "Hi {{recipient_name}},\n\nI'm {{sender_name}} from {{company_name}}. I'd love to show you how {{product_name}} could help your team.\n\nWould {{meeting_date}} work for a short call?",
  content_type: "PLAIN_TEXT",
  is_active: true,
};

function variablesIn(...texts: string[]): string[] {
  const names: string[] = [];
  for (const text of texts) for (const m of text.matchAll(PLACEHOLDER)) if (!names.includes(m[1])) names.push(m[1]);
  return names;
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [builtins, setBuiltins] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [noCompany, setNoCompany] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [editing, setEditing] = useState<EmailTemplate | "new" | null>(null);
  const [form, setForm] = useState<EmailTemplateInput>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [previewFor, setPreviewFor] = useState<EmailTemplate | null>(null);
  const [previewValues, setPreviewValues] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<TemplatePreview | null>(null);
  const [previewing, setPreviewing] = useState(false);

  const reload = useCallback(async () => {
    try {
      setTemplates(await api.listTemplates());
    } catch (err) {
      if (isMissingCompany(err)) setNoCompany(true);
      else setError(err instanceof ApiError ? err.message : "Could not load templates.");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listTemplates()
      .then((list) => {
        if (!cancelled) setTemplates(list);
      })
      .catch((err) => {
        if (cancelled) return;
        if (isMissingCompany(err)) setNoCompany(true);
        else setError(err instanceof ApiError ? err.message : "Could not load templates.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    api
      .builtinTemplateVariables()
      .then(setBuiltins)
      .catch(() => setBuiltins([]));
  }, []);

  const formVariables = useMemo(() => variablesIn(form.subject_template, form.body_template), [form]);

  function startNew() {
    setEditing("new");
    setForm(EMPTY);
    setErrors({});
    setSuccess("");
  }

  function startEdit(t: EmailTemplate) {
    setEditing(t);
    setForm({
      name: t.name,
      description: t.description,
      category: t.category,
      subject_template: t.subject_template,
      body_template: t.body_template,
      content_type: t.content_type,
      is_active: t.is_active,
    });
    setErrors({});
    setSuccess("");
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    const e: Record<string, string> = {};
    if (!form.name.trim()) e.name = "Name is required";
    if (!form.subject_template.trim()) e.subject_template = "Subject is required";
    else if (/[\r\n]/.test(form.subject_template)) e.subject_template = "Subject must be a single line";
    if (!form.body_template.trim()) e.body_template = "Body is required";
    setErrors(e);
    if (Object.keys(e).length || editing === null) return;

    const payload: EmailTemplateInput = {
      ...form,
      name: form.name.trim(),
      description: form.description?.trim() || null,
      category: form.category?.trim() || null,
    };
    setSaving(true);
    try {
      if (editing === "new") await api.createTemplate(payload);
      else await api.updateTemplate(editing.id, payload);
      setSuccess(editing === "new" ? "Template created." : "Template saved.");
      setEditing(null);
      await reload();
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setError(err.message);
      } else setError("Could not save the template.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(t: EmailTemplate) {
    if (!window.confirm(`Delete the template "${t.name}"?`)) return;
    try {
      await api.deleteTemplate(t.id);
      if (previewFor?.id === t.id) setPreviewFor(null);
      setSuccess("Template deleted.");
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete the template.");
    }
  }

  function openPreview(t: EmailTemplate) {
    setPreviewFor(t);
    setPreview(null);
    setPreviewValues(Object.fromEntries(t.variables.filter((v) => !builtins.includes(v) || v === "recipient_name").map((v) => [v, ""])));
  }

  async function runPreview() {
    if (!previewFor) return;
    setPreviewing(true);
    setError("");
    try {
      const { recipient_name, ...variables } = previewValues;
      setPreview(await api.previewTemplate(previewFor.id, { variables, recipient_name: recipient_name || null }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not render the preview.");
    } finally {
      setPreviewing(false);
    }
  }

  if (loading) return <LoadingScreen />;
  if (noCompany) {
    return (
      <>
        <PageHeader title="Email Templates" />
        <NeedsCompany />
      </>
    );
  }

  const setField = (key: keyof EmailTemplateInput) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value }));

  return (
    <>
      <PageHeader
        title="Email Templates"
        description="Reusable emails with {{ variable }} placeholders. Pick one on the AI Email Agent page to base a draft on it."
      />
      <Alert kind="success">{success}</Alert>
      <Alert kind="error">{error}</Alert>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Your templates</h2>
          <button type="button" className="btn" onClick={startNew}>
            + New template
          </button>
        </div>
        {templates.length === 0 ? (
          <p className="muted">No templates yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Format</th>
                  <th>Variables</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <strong>{t.name}</strong>
                      {t.description && <div className="muted">{t.description}</div>}
                    </td>
                    <td>{t.category ?? "—"}</td>
                    <td>{t.content_type === "HTML" ? "HTML" : "Plain text"}</td>
                    <td className="muted">{t.variables.join(", ") || "—"}</td>
                    <td>
                      <span className={`badge ${t.is_active ? "badge-success" : ""}`}>{t.is_active ? "Active" : "Inactive"}</span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        <button className="btn btn-secondary btn-small" onClick={() => openPreview(t)}>
                          Preview
                        </button>
                        <button className="btn btn-secondary btn-small" onClick={() => startEdit(t)}>
                          Edit
                        </button>
                        <button className="btn btn-danger btn-small" onClick={() => remove(t)}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing !== null && (
        <form className="card" onSubmit={onSave} noValidate>
          <h2>{editing === "new" ? "New template" : `Edit ${editing.name}`}</h2>
          <div className="grid grid-2">
            <Field label="Name *" htmlFor="name" error={errors.name}>
              <input id="name" value={form.name} onChange={setField("name")} className={errors.name ? "invalid" : ""} />
            </Field>
            <Field label="Category" htmlFor="category" error={errors.category}>
              <input id="category" value={form.category ?? ""} onChange={setField("category")} placeholder="Sales" />
            </Field>
            <Field label="Description" htmlFor="description" error={errors.description} className="span-2">
              <input id="description" value={form.description ?? ""} onChange={setField("description")} />
            </Field>
            <Field label="Subject *" htmlFor="subject_template" error={errors.subject_template} className="span-2">
              <input
                id="subject_template"
                value={form.subject_template}
                onChange={setField("subject_template")}
                className={errors.subject_template ? "invalid" : ""}
              />
            </Field>
            <Field
              label="Body *"
              htmlFor="body_template"
              error={errors.body_template}
              className="span-2"
              hint={`Placeholders: {{ variable_name }} (letters, digits, underscores). Filled automatically: ${builtins.join(", ")}.`}
            >
              <textarea
                id="body_template"
                rows={10}
                value={form.body_template}
                onChange={setField("body_template")}
                className={errors.body_template ? "invalid" : ""}
              />
            </Field>
            <Field label="Format" htmlFor="content_type">
              <select id="content_type" value={form.content_type} onChange={(e) => setForm((f) => ({ ...f, content_type: e.target.value as EmailFormat }))}>
                <option value="PLAIN_TEXT">Plain text</option>
                <option value="HTML">HTML</option>
              </select>
            </Field>
            <label className="checkbox" style={{ alignSelf: "end" }}>
              <input type="checkbox" checked={form.is_active} onChange={setField("is_active")} />
              Active
            </label>
            <div className="span-2 muted">Variables in this template: {formVariables.join(", ") || "none"}</div>
          </div>
          <div className="form-actions">
            <SubmitButton loading={saving}>{editing === "new" ? "Create template" : "Save template"}</SubmitButton>
            <button type="button" className="btn btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {previewFor && (
        <div className="card">
          <h2>Preview: {previewFor.name}</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            Company, sender and recipient values are filled automatically; enter the rest.
          </p>
          <div className="grid grid-2">
            {Object.keys(previewValues).map((name) => (
              <Field key={name} label={name} htmlFor={`pv-${name}`}>
                <input
                  id={`pv-${name}`}
                  value={previewValues[name]}
                  onChange={(e) => setPreviewValues((v) => ({ ...v, [name]: e.target.value }))}
                />
              </Field>
            ))}
          </div>
          <div className="form-actions">
            <SubmitButton type="button" loading={previewing} onClick={runPreview}>
              Render preview
            </SubmitButton>
          </div>
          {preview && (
            <div style={{ marginTop: 14 }}>
              {preview.missing_variables.length > 0 && (
                <Alert kind="warning">Unfilled: {preview.missing_variables.join(", ")}</Alert>
              )}
              <div className="muted">Subject</div>
              <div className="preview" style={{ marginBottom: 10 }}>
                {preview.subject}
              </div>
              <div className="muted">Body {preview.content_type === "HTML" ? "(HTML source)" : ""}</div>
              <div className="preview">{preview.body}</div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
