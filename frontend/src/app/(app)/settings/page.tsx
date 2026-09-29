"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { Icon, type IconName } from "@/components/Icon";
import { Badge, buttonClass, Card, CardHeader, initials, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/Workspace";
import { api } from "@/lib/api";
import { getExpiresAt } from "@/lib/session";
import type { EmailAccount } from "@/lib/types";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm font-medium break-words text-slate-800 sm:text-right">{children}</span>
    </div>
  );
}

const SECURITY: { icon: IconName; title: string; text: string }[] = [
  { icon: "shield", title: "Encrypted credentials", text: "SMTP passwords and Gmail OAuth tokens are encrypted at rest and never returned by the API." },
  { icon: "user", title: "Company isolation", text: "Every request is scoped to your company; other companies' data is never visible." },
  { icon: "clock", title: "Short-lived sessions", text: "You are signed out automatically when your session token expires." },
];

const PROVIDERS: { name: string; role: string; tone: "info" | "neutral" }[] = [
  { name: "Groq", role: "Primary provider", tone: "info" },
  { name: "Gemini", role: "Secondary provider", tone: "neutral" },
  { name: "Mock", role: "Final fallback (template-based)", tone: "neutral" },
];

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const workspace = useWorkspace();
  const [accounts, setAccounts] = useState<EmailAccount[] | null>(null);
  const [expiresAt] = useState(() => getExpiresAt());

  useEffect(() => {
    api
      .listEmailAccounts()
      .then(setAccounts)
      .catch(() => setAccounts([]));
  }, []);

  const defaultAccount = accounts?.find((a) => a.is_default) ?? null;

  return (
    <>
      <PageHeader title="Settings" description="Your account, security and configuration overview. Secrets are never shown here." />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader icon="user" title="Account" />
          <div className="p-5">
            <div className="mb-3 flex items-center gap-3">
              <span className="grid size-11 place-items-center rounded-full bg-blue-600 text-sm font-bold text-white" aria-hidden="true">
                {initials(user?.name)}
              </span>
              <div className="min-w-0">
                <p className="truncate font-semibold text-slate-900">{user?.name}</p>
                <p className="truncate text-sm text-slate-500">{user?.email}</p>
              </div>
            </div>
            <div className="divide-y divide-slate-100">
              <Row label="Company workspace">
                {workspace?.companyName ?? (
                  <Link href="/company" className="font-semibold">
                    Create company profile
                  </Link>
                )}
              </Row>
              <Row label="Member since">{user ? new Date(user.created_at).toLocaleDateString() : "—"}</Row>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader icon="shield" title="Security" />
          <div className="space-y-3 p-5">
            {SECURITY.map((item) => (
              <div key={item.title} className="flex gap-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600">
                  <Icon name={item.icon} />
                </span>
                <div>
                  <p className="text-sm font-semibold text-slate-800">{item.title}</p>
                  <p className="text-xs text-slate-500">{item.text}</p>
                </div>
              </div>
            ))}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
              <p className="text-xs text-slate-500">
                {expiresAt ? `This session expires at ${new Date(expiresAt).toLocaleTimeString()}.` : "Session active."}
              </p>
              <button type="button" className={buttonClass("secondary", "sm")} onClick={() => logout()}>
                <Icon name="logout" className="size-3.5" /> Log out
              </button>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader icon="bot" title="AI provider" description="Configured on the server with environment variables." />
          <div className="p-5">
            <ol className="space-y-2">
              {PROVIDERS.map((p, index) => (
                <li key={p.name} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2.5">
                  <span className="grid size-6 place-items-center rounded-full bg-white text-xs font-bold text-slate-600 ring-1 ring-slate-200">
                    {index + 1}
                  </span>
                  <span className="flex-1 text-sm font-semibold text-slate-800">{p.name}</span>
                  <Badge tone={p.tone}>{p.role}</Badge>
                </li>
              ))}
            </ol>
            <p className="mt-3 text-xs text-slate-500">
              If a provider is unavailable, the next one writes the draft and the Email Agent shows which provider was used. API keys stay on
              the server and are never sent to the browser.
            </p>
          </div>
        </Card>

        <Card>
          <CardHeader
            icon="mail"
            title="Email configuration"
            actions={
              <Link href="/email-accounts" className="text-xs font-semibold">
                Manage
              </Link>
            }
          />
          <div className="divide-y divide-slate-100 px-5 py-2">
            <Row label="Email accounts">{accounts === null ? "…" : accounts.length}</Row>
            <Row label="Active">{accounts === null ? "…" : accounts.filter((a) => a.is_active).length}</Row>
            <Row label="Gmail OAuth connected">{accounts === null ? "…" : accounts.filter((a) => a.account_type === "OAUTH" && a.oauth_connected).length}</Row>
            <Row label="Default sender">{accounts === null ? "…" : (defaultAccount?.email_address ?? "Not set")}</Row>
          </div>
        </Card>
      </div>
    </>
  );
}
