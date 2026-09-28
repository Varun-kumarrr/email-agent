"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Alert, LoadingScreen, PageHeader } from "@/components/ui";
import { api, ApiError, isNotFound } from "@/lib/api";
import type { Company, EmailConfig, EmailHistoryPage, Preferences, Signature } from "@/lib/types";

interface Status {
  company: Company | null;
  config: EmailConfig | null;
  signature: Signature | null;
  preferences: Preferences | null;
  history: EmailHistoryPage | null;
  sentTotal: number;
}

/** Resolve to null for "not created yet" (404) and rethrow anything else. */
async function optional<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (err) {
    if (isNotFound(err)) return null;
    throw err;
  }
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const company = await optional(api.getCompany());
        if (!company) {
          setStatus({ company: null, config: null, signature: null, preferences: null, history: null, sentTotal: 0 });
          return;
        }
        const [config, signature, preferences, history, sent] = await Promise.all([
          optional(api.getEmailConfig()),
          optional(api.getSignature()),
          api.getPreferences(),
          api.history(1, 5),
          api.history(1, 1, "SENT"),
        ]);
        setStatus({ company, config, signature, preferences, history, sentTotal: sent.total });
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load your dashboard.");
      }
    })();
  }, []);

  if (error) return <Alert kind="error">{error}</Alert>;
  if (!status) return <LoadingScreen />;

  const { company, config, signature, preferences, history, sentTotal } = status;
  const steps = [
    { done: !!company, label: "Create your company profile", href: "/company", detail: company?.name },
    { done: !!config, label: "Configure your SMTP email account", href: "/email-config", detail: config?.email },
    {
      done: !!config?.last_test_success,
      label: "Send a successful test email",
      href: "/email-config",
      detail: config?.last_test_success === false ? "Last test failed" : undefined,
    },
    {
      done: !!signature,
      label: "Set up your email signature",
      href: "/signature",
      detail: signature ? (signature.append_automatically ? "Appended automatically" : "Manual") : "Optional",
    },
    { done: !!preferences?.updated_at, label: "Review sending preferences", href: "/preferences", detail: "Optional" },
    { done: sentTotal > 0, label: "Generate and send your first email", href: "/agent" },
  ];
  const next = steps.find((s) => !s.done);

  return (
    <>
      <PageHeader title={`Welcome, ${user?.name ?? ""}`} description="Your email agent at a glance." />

      {next && (
        <Alert kind="info">
          Next step: <Link href={next.href}>{next.label}</Link>
        </Alert>
      )}

      <div className="grid grid-3">
        <div className="card">
          <div className="muted">Emails sent today</div>
          <div className="stat">{preferences ? `${preferences.sent_today} / ${preferences.daily_send_limit}` : "—"}</div>
        </div>
        <div className="card">
          <div className="muted">Total emails in history</div>
          <div className="stat">{history?.total ?? 0}</div>
        </div>
        <div className="card">
          <div className="muted">Sending account</div>
          <div style={{ fontWeight: 600, wordBreak: "break-all" }}>{config?.email ?? "Not configured"}</div>
        </div>
      </div>

      <div className="card">
        <h2>Setup checklist</h2>
        <ul className="steps">
          {steps.map((step) => (
            <li key={step.label}>
              <span>
                <span className={`badge ${step.done ? "badge-success" : ""}`} style={{ marginRight: 10 }}>
                  {step.done ? "Done" : "To do"}
                </span>
                {step.label}
                {step.detail && <span className="muted"> — {step.detail}</span>}
              </span>
              <Link className="btn btn-secondary btn-small" href={step.href}>
                {step.done ? "View" : "Start"}
              </Link>
            </li>
          ))}
        </ul>
      </div>

      {history && history.items.length > 0 && (
        <div className="card">
          <h2>Recent emails</h2>
          <div className="table-wrap">
            <table>
              <tbody>
                {history.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.recipient}</td>
                    <td>{item.subject}</td>
                    <td>
                      <span className={`badge ${item.status === "SENT" ? "badge-success" : "badge-danger"}`}>{item.status}</span>
                    </td>
                    <td className="muted">{new Date(item.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link href="/history">View all history →</Link>
        </div>
      )}
    </>
  );
}
