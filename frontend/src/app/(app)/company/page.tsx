"use client";

import { useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ListEditor } from "@/components/ListEditor";
import { Alert, Field, LoadingScreen, PageHeader, SubmitButton } from "@/components/ui";
import { api, ApiError, isNotFound } from "@/lib/api";
import type {
  Company,
  CompanyInput,
  ServiceItem,
  SocialLinkItem,
  TargetCustomerItem,
  ValuePropositionItem,
} from "@/lib/types";

type TextKey =
  | "name"
  | "description"
  | "website"
  | "industry"
  | "location"
  | "contact_person"
  | "contact_email"
  | "contact_phone"
  | "address";

interface FormState {
  name: string;
  description: string;
  website: string;
  industry: string;
  location: string;
  contact_person: string;
  contact_email: string;
  contact_phone: string;
  address: string;
  services: ServiceItem[];
  target_customers: TargetCustomerItem[];
  value_propositions: ValuePropositionItem[];
  social_links: SocialLinkItem[];
}

const EMPTY: FormState = {
  name: "",
  description: "",
  website: "",
  industry: "",
  location: "",
  contact_person: "",
  contact_email: "",
  contact_phone: "",
  address: "",
  services: [],
  target_customers: [],
  value_propositions: [],
  social_links: [],
};

function fromCompany(c: Company): FormState {
  return {
    name: c.name,
    description: c.description,
    website: c.website ?? "",
    industry: c.industry ?? "",
    location: c.location ?? "",
    contact_person: c.contact_person ?? "",
    contact_email: c.contact_email ?? "",
    contact_phone: c.contact_phone ?? "",
    address: c.address ?? "",
    services: c.services.map((s) => ({ name: s.name, description: s.description ?? "" })),
    target_customers: c.target_customers.map((t) => ({ segment: t.segment, description: t.description ?? "" })),
    value_propositions: c.value_propositions.map((v) => ({ statement: v.statement })),
    social_links: c.social_links.map((l) => ({ platform: l.platform, url: l.url })),
  };
}

const orNull = (value: string) => (value.trim() ? value.trim() : null);

function toInput(f: FormState): CompanyInput {
  return {
    name: f.name.trim(),
    description: f.description.trim(),
    website: orNull(f.website),
    industry: orNull(f.industry),
    location: orNull(f.location),
    contact_person: orNull(f.contact_person),
    contact_email: orNull(f.contact_email),
    contact_phone: orNull(f.contact_phone),
    address: orNull(f.address),
    // Drop rows the user left completely empty.
    services: f.services
      .filter((s) => s.name.trim() || s.description?.trim())
      .map((s) => ({ name: s.name.trim(), description: orNull(s.description ?? "") })),
    target_customers: f.target_customers
      .filter((t) => t.segment.trim() || t.description?.trim())
      .map((t) => ({ segment: t.segment.trim(), description: orNull(t.description ?? "") })),
    value_propositions: f.value_propositions
      .filter((v) => v.statement.trim())
      .map((v) => ({ statement: v.statement.trim() })),
    social_links: f.social_links
      .filter((l) => l.platform.trim() || l.url.trim())
      .map((l) => ({ platform: l.platform.trim(), url: l.url.trim() })),
  };
}

function validate(f: FormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!f.name.trim()) errors.name = "Company name is required";
  if (!f.description.trim()) errors.description = "Description is required";
  if (f.contact_email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.contact_email.trim()))
    errors.contact_email = "Enter a valid email address";
  return errors;
}

export default function CompanyPage() {
  const { refreshUser } = useAuth();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [exists, setExists] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    api
      .getCompany()
      .then((company) => {
        setForm(fromCompany(company));
        setExists(true);
      })
      .catch((err) => {
        if (!isNotFound(err)) setError(err instanceof ApiError ? err.message : "Could not load the company profile.");
      })
      .finally(() => setLoading(false));
  }, []);

  const set = (key: TextKey) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSuccess("");
    setError("");
    const clientErrors = validate(form);
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length) return;

    setSaving(true);
    try {
      const saved = exists ? await api.updateCompany(toInput(form)) : await api.createCompany(toInput(form));
      setForm(fromCompany(saved));
      setSuccess(exists ? "Company profile updated." : "Company profile created. Next: configure your email account.");
      if (!exists) await refreshUser();
      setExists(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setError(err.message);
      } else {
        setError("Could not save the company profile.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingScreen />;

  const text = (key: TextKey, label: string, opts: { type?: string; hint?: string; placeholder?: string } = {}) => (
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
      <PageHeader
        title="Company Profile"
        description="This information is the context the AI agent uses to write your emails. Only include facts you want in emails."
      />
      {!exists && <Alert kind="info">You haven&apos;t created a company profile yet. Fill in the form to create one.</Alert>}
      <Alert kind="success">{success}</Alert>
      <Alert kind="error">{error}</Alert>

      <form onSubmit={onSubmit} noValidate>
        <div className="card">
          <h2>Company</h2>
          <div className="grid grid-2">
            {text("name", "Company name *", { placeholder: "ABC Technologies" })}
            {text("website", "Website", { placeholder: "https://www.example.com" })}
            <Field label="Description / overview *" htmlFor="description" error={errors.description} className="span-2">
              <textarea
                id="description"
                value={form.description}
                onChange={set("description")}
                placeholder="What the company does and for whom."
                className={errors.description ? "invalid" : ""}
              />
            </Field>
            {text("industry", "Industry", { placeholder: "Software" })}
            {text("location", "Location", { placeholder: "Bengaluru, India" })}
          </div>
        </div>

        <div className="card">
          <h2>Offering</h2>
          <div className="grid">
            <ListEditor<ServiceItem>
              name="services"
              label="Services / products"
              items={form.services}
              fields={[
                { key: "name", placeholder: "Name" },
                { key: "description", placeholder: "Short description (optional)" },
              ]}
              empty={{ name: "", description: "" }}
              onChange={(services) => setForm((f) => ({ ...f, services }))}
              errors={errors}
              addLabel="Add service"
            />
            <ListEditor<TargetCustomerItem>
              name="target_customers"
              label="Target customers"
              items={form.target_customers}
              fields={[
                { key: "segment", placeholder: "Segment" },
                { key: "description", placeholder: "Details (optional)" },
              ]}
              empty={{ segment: "", description: "" }}
              onChange={(target_customers) => setForm((f) => ({ ...f, target_customers }))}
              errors={errors}
              addLabel="Add target customer"
            />
            <ListEditor<ValuePropositionItem>
              name="value_propositions"
              label="Value propositions"
              items={form.value_propositions}
              fields={[{ key: "statement", placeholder: "Value proposition" }]}
              empty={{ statement: "" }}
              onChange={(value_propositions) => setForm((f) => ({ ...f, value_propositions }))}
              errors={errors}
              addLabel="Add value proposition"
            />
          </div>
        </div>

        <div className="card">
          <h2>Contact information</h2>
          <div className="grid grid-2">
            {text("contact_person", "Contact person")}
            {text("contact_email", "Contact email", { type: "email" })}
            {text("contact_phone", "Phone", { placeholder: "+91 98765 43210" })}
            {text("address", "Address")}
          </div>
        </div>

        <div className="card">
          <h2>Social media & links</h2>
          <ListEditor<SocialLinkItem>
            name="social_links"
            label="Links"
            items={form.social_links}
            fields={[
              { key: "platform", placeholder: "Platform (e.g. LinkedIn)" },
              { key: "url", placeholder: "https://…", type: "url" },
            ]}
            empty={{ platform: "", url: "" }}
            onChange={(social_links) => setForm((f) => ({ ...f, social_links }))}
            errors={errors}
            addLabel="Add link"
          />
        </div>

        <div className="form-actions">
          <SubmitButton loading={saving}>{exists ? "Save changes" : "Create company profile"}</SubmitButton>
        </div>
      </form>
    </>
  );
}
