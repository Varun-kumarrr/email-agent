"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Icon, type IconName } from "@/components/Icon";
import { Alert, Badge, buttonClass, Card, CardHeader, cx, EmptyState, LoadingScreen, PageHeader, StatCard, StatusBadge, TestBadge } from "@/components/ui";
import { api, ApiError, isNotFound } from "@/lib/api";
import type { Company, EmailAccount, EmailHistoryItem, EmailHistoryPage, EmailTemplate, Preferences, Signature } from "@/lib/types";

interface Status {
  company: Company | null;
  accounts: EmailAccount[];
  signature: Signature | null;
  preferences: Preferences | null;
  history: EmailHistoryPage | null;
  templates: EmailTemplate[];
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

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

const ACTIVITY_ICON: Record<string, { icon: IconName; cls: string }> = {
  SENT: { icon: "checkCircle", cls: "bg-emerald-50 text-emerald-600" },
  FAILED: { icon: "xCircle", cls: "bg-red-50 text-red-600" },
  RETRYING: { icon: "refresh", cls: "bg-amber-50 text-amber-600" },
};

function ActivityItem({ item }: { item: EmailHistoryItem }) {
  const style = ACTIVITY_ICON[item.status] ?? { icon: "clock" as IconName, cls: "bg-blue-50 text-blue-600" };
  return (
    <li className="flex gap-3 py-3 first:pt-0 last:pb-0">
      <span className={cx("grid size-8 shrink-0 place-items-center rounded-lg", style.cls)}>
        <Icon name={style.icon} className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="truncate text-sm font-semibold text-slate-800">{item.subject}</p>
          <span className="shrink-0 text-xs text-slate-400">{timeAgo(item.sent_at ?? item.created_at)}</span>
        </div>
        <p className="truncate text-xs text-slate-500">To {item.recipient}</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <StatusBadge status={item.status} />
          {item.is_test && <TestBadge />}
        </div>
      </div>
    </li>
  );
}

const QUICK_ACTIONS: { href: string; label: string; description: string; icon: IconName }[] = [
  { href: "/agent", label: "Generate email", description: "Draft with the AI agent", icon: "sparkles" },
  { href: "/email-accounts", label: "Add email account", description: "SMTP or Gmail OAuth", icon: "mail" },
  { href: "/templates", label: "Create template", description: "Reusable subject and body", icon: "fileText" },
  { href: "/company", label: "Edit company profile", description: "Context for the agent", icon: "building" },
];

export default function DashboardPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const company = await optional(api.getCompany());
        if (!company) {
          setStatus({ company: null, accounts: [], signature: null, preferences: null, history: null, templates: [], sentTotal: 0 });
          return;
        }
        const [accounts, signature, preferences, history, sent, templates] = await Promise.all([
          api.listEmailAccounts(),
          optional(api.getSignature()),
          api.getPreferences(),
          api.history(1, 5),
          api.history(1, 1, "SENT"),
          api.listTemplates(),
        ]);
        setStatus({ company, accounts, signature, preferences, history, templates, sentTotal: sent.total });
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load your dashboard.");
      }
    })();
  }, []);

  const header = <PageHeader title={`Welcome, ${user?.name ?? ""}`} description="Your email agent at a glance: accounts, activity and next steps." />;
  if (error)
    return (
      <>
        {header}
        <Alert kind="error">{error}</Alert>
      </>
    );
  if (!status)
    return (
      <>
        {header}
        <LoadingScreen />
      </>
    );

  const { company, accounts, signature, preferences, history, templates, sentTotal } = status;
  const account = accounts.find((a) => a.is_default) ?? accounts[0] ?? null;
  const activeAccounts = accounts.filter((a) => a.is_active).length;
  const steps = [
    { done: !!company, label: "Create your company profile", href: "/company", detail: company?.name },
    { done: !!account, label: "Add an email account", href: "/email-accounts", detail: account?.email_address },
    {
      done: !!account?.last_test_success,
      label: "Send a successful test email",
      href: "/email-accounts",
      detail: account?.last_test_success === false ? "Last test failed" : undefined,
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
  const doneCount = steps.filter((s) => s.done).length;

  return (
    <>
      {header}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard
          label="Email accounts"
          icon="mail"
          href="/email-accounts"
          value={accounts.length}
          caption={accounts.length ? `${activeAccounts} active` : "Add your first account"}
          captionTone={accounts.length ? "success" : "info"}
        />
        <StatCard
          label="Emails sent"
          icon="send"
          href="/history"
          value={sentTotal}
          caption={preferences ? `${preferences.sent_today} of ${preferences.daily_send_limit} today` : undefined}
          captionTone="info"
        />
        <StatCard
          label="Templates"
          icon="fileText"
          href="/templates"
          value={templates.length}
          caption={templates.length ? `${templates.filter((t) => t.is_active).length} active` : "None yet"}
          captionTone={templates.length ? "success" : "muted"}
        />
        <StatCard
          label="Email activity"
          icon="history"
          href="/history"
          value={history?.total ?? 0}
          caption="All sends and tests"
          captionTone="muted"
        />
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="space-y-5">
          <Card>
            <CardHeader icon="zap" title="Quick actions" />
            <div className="grid grid-cols-1 gap-2.5 p-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              {QUICK_ACTIONS.map((action) => (
                <Link
                  key={action.href}
                  href={action.href}
                  className="group flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3 transition hover:border-blue-200 hover:bg-blue-50/50"
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white text-blue-600 shadow-xs ring-1 ring-slate-200">
                    <Icon name={action.icon} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-slate-800 group-hover:text-blue-700">{action.label}</span>
                    <span className="block truncate text-xs text-slate-500">{action.description}</span>
                  </span>
                </Link>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader icon="checkCircle" title="Setup checklist" meta={`${doneCount} of ${steps.length} done`} />
            <ul className="space-y-2 p-4">
              {steps.map((step) => (
                <li key={step.label} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
                  <span
                    className={cx(
                      "grid size-5 shrink-0 place-items-center rounded-full",
                      step.done ? "bg-emerald-500 text-white" : "border-2 border-slate-300",
                    )}
                    aria-hidden="true"
                  >
                    {step.done && <Icon name="check" className="size-3" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-800">{step.label}</p>
                    {step.detail && <p className="truncate text-xs text-slate-500">{step.detail}</p>}
                  </div>
                  {step.done ? (
                    <Badge tone="success">Done</Badge>
                  ) : (
                    <Link href={step.href} className={buttonClass("secondary", "sm")}>
                      Start
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <Card>
          <CardHeader
            icon="clock"
            title="Recent email activity"
            meta={history?.items.length ? `Latest ${history.items.length}` : undefined}
            actions={
              history?.items.length ? (
                <Link href="/history" className="text-xs font-semibold">
                  View all
                </Link>
              ) : undefined
            }
          />
          <div className="p-4">
            {history && history.items.length > 0 ? (
              <ul className="divide-y divide-slate-100">
                {history.items.map((item) => (
                  <ActivityItem key={item.id} item={item} />
                ))}
              </ul>
            ) : (
              <EmptyState
                title="No email activity yet"
                description="Generate your first email to see activity here."
                action={
                  <Link href="/agent" className={buttonClass("primary", "sm")}>
                    <Icon name="sparkles" className="size-3.5" /> Generate email
                  </Link>
                }
              />
            )}
          </div>
        </Card>
      </div>
    </>
  );
}
