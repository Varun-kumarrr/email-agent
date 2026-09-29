"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Icon } from "@/components/Icon";
import { Alert, Badge, buttonClass, Card, CardHeader, EmptyState, Field, LoadingScreen, PageHeader, SubmitButton } from "@/components/ui";
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

  const header = (
    <PageHeader
      title="Email Templates"
      description="Reusable emails with {{ variable }} placeholders. Use one on the AI Email Agent page to base a draft on it."
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

  const setField = (key: keyof EmailTemplateInput) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value }));

  return (
    <>
      {header}
      <Alert kind="success" onDismiss={success ? () => setSuccess("") : undefined}>
        {success}
      </Alert>
      <Alert kind="error" onDismiss={error ? () => setError("") : undefined}>
        {error}
      </Alert>

      <Card>
        <CardHeader
          icon="fileText"
          title="Your templates"
          meta={templates.length ? `${templates.length} total` : undefined}
          actions={
            <button type="button" className={buttonClass("primary", "sm")} onClick={startNew}>
              <Icon name="plus" className="size-3.5" /> Create template
            </button>
          }
        />
        {templates.length === 0 ? (
          <EmptyState
            icon="fileText"
            title="No templates yet"
            description="Create a reusable template for emails you send often, then use it in the AI Email Agent."
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
            {templates.map((t) => (
              <article key={t.id} className="flex flex-col rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:shadow-sm">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-slate-900">{t.name}</h3>
                  <Badge tone={t.is_active ? "success" : "neutral"}>{t.is_active ? "Active" : "Inactive"}</Badge>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {t.category && <Badge tone="info">{t.category}</Badge>}
                  <Badge>{t.content_type === "HTML" ? "HTML" : "Plain text"}</Badge>
                </div>
                {t.description && <p className="mt-2 text-sm text-slate-600">{t.description}</p>}
                <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2">
                  <p className="line-clamp-3 text-xs whitespace-pre-line text-slate-600">{t.body_template}</p>
                </div>
                {t.variables.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1">
                    {t.variables.map((v) => (
                      <code key={v} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
                        {v}
                      </code>
                    ))}
                  </div>
                )}
                <p className="mt-3 text-xs text-slate-400">Updated {new Date(t.updated_at).toLocaleDateString()}</p>
                <div className="mt-auto flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                  {t.is_active && (
                    <Link href={`/agent?template=${encodeURIComponent(t.id)}`} className={buttonClass("primary", "sm")}>
                      <Icon name="sparkles" className="size-3.5" /> Use
                    </Link>
                  )}
                  <button className={buttonClass("secondary", "sm")} onClick={() => openPreview(t)}>
                    <Icon name="eye" className="size-3.5" /> Preview
                  </button>
                  <button className={buttonClass("secondary", "sm")} onClick={() => startEdit(t)}>
                    <Icon name="edit" className="size-3.5" /> Edit
                  </button>
                  <button
                    className={buttonClass("ghost", "sm", "ml-auto px-2 text-red-600 hover:bg-red-50 hover:text-red-700")}
                    onClick={() => remove(t)}
                    aria-label={`Delete template ${t.name}`}
                    title="Delete"
                  >
                    <Icon name="trash" className="size-3.5" />
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Card>

      {editing !== null && (
        <Card className="mt-5">
          <form onSubmit={onSave} noValidate>
            <CardHeader icon={editing === "new" ? "plus" : "edit"} title={editing === "new" ? "Create template" : `Edit ${editing.name}`} />
            <div className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
              <Field label="Name *" htmlFor="name" error={errors.name}>
                <input id="name" value={form.name} onChange={setField("name")} className={errors.name ? "invalid" : ""} />
              </Field>
              <Field label="Category" htmlFor="category" error={errors.category}>
                <input id="category" value={form.category ?? ""} onChange={setField("category")} placeholder="Sales" />
              </Field>
              <Field label="Description" htmlFor="description" error={errors.description} className="sm:col-span-2">
                <input id="description" value={form.description ?? ""} onChange={setField("description")} />
              </Field>
              <Field label="Subject *" htmlFor="subject_template" error={errors.subject_template} className="sm:col-span-2">
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
                className="sm:col-span-2"
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
              <label className="flex items-center gap-2 self-end pb-2 text-sm font-medium text-slate-700">
                <input type="checkbox" checked={form.is_active} onChange={setField("is_active")} />
                Active
              </label>
              <p className="text-xs text-slate-500 sm:col-span-2">Variables in this template: {formVariables.join(", ") || "none"}</p>
            </div>
            <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-3.5">
              <button type="button" className={buttonClass("secondary")} onClick={() => setEditing(null)}>
                Cancel
              </button>
              <SubmitButton loading={saving}>{editing === "new" ? "Create template" : "Save template"}</SubmitButton>
            </div>
          </form>
        </Card>
      )}

      {previewFor && (
        <Card className="mt-5">
          <CardHeader
            icon="eye"
            title={`Preview: ${previewFor.name}`}
            description="Company, sender and recipient values are filled automatically; enter the rest."
            actions={
              <button type="button" className={buttonClass("ghost", "sm")} onClick={() => setPreviewFor(null)} aria-label="Close preview">
                <Icon name="close" className="size-3.5" />
              </button>
            }
          />
          <div className="space-y-4 p-5">
            {Object.keys(previewValues).length > 0 && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {Object.keys(previewValues).map((name) => (
                  <Field key={name} label={name} htmlFor={`pv-${name}`}>
                    <input id={`pv-${name}`} value={previewValues[name]} onChange={(e) => setPreviewValues((v) => ({ ...v, [name]: e.target.value }))} />
                  </Field>
                ))}
              </div>
            )}
            <SubmitButton type="button" variant="secondary" loading={previewing} onClick={runPreview}>
              Render preview
            </SubmitButton>
            {preview && (
              <div className="space-y-3">
                {preview.missing_variables.length > 0 && <Alert kind="warning">Unfilled: {preview.missing_variables.join(", ")}</Alert>}
                <div className="overflow-hidden rounded-xl border border-slate-200">
                  <div className="border-b border-slate-100 bg-slate-50/70 px-4 py-2.5 text-sm">
                    <span className="text-slate-500">Subject: </span>
                    <span className="font-semibold text-slate-900">{preview.subject}</span>
                  </div>
                  <pre className="px-4 py-3 font-sans text-sm whitespace-pre-wrap text-slate-700">{preview.body}</pre>
                </div>
                {preview.content_type === "HTML" && <p className="text-xs text-slate-500">Shown as HTML source.</p>}
              </div>
            )}
          </div>
        </Card>
      )}
    </>
  );
}
