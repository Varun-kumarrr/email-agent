"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";

import { Icon } from "@/components/Icon";
import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, buttonClass, Card, CardHeader, cx, EmptyState, LoadingScreen, PageHeader, StatusBadge, TestBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { FINAL_STATUSES, type EmailAccount, type EmailHistoryItem, type EmailHistoryPage, type EmailStatus } from "@/lib/types";

const PAGE_SIZE = 10;

const FILTERS: { value: EmailStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "SENT", label: "Sent" },
  { value: "FAILED", label: "Failed" },
  { value: "QUEUED", label: "Pending" },
  { value: "SENDING", label: "Sending" },
  { value: "RETRYING", label: "Retrying" },
];

function providerLabel(account: EmailAccount | undefined): string {
  if (!account) return "Deleted account";
  const name = account.provider === "GMAIL" ? "Gmail" : account.provider === "OUTLOOK" ? "Outlook" : "SMTP";
  return account.account_type === "OAUTH" ? `${name} · OAuth` : name === "SMTP" ? "SMTP" : `${name} · SMTP`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function EmailDetails({ item }: { item: EmailHistoryItem }) {
  return (
    <>
      <dl className="mb-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-slate-500">Sender</dt>
          <dd className="font-medium break-all text-slate-800">{item.sender_name ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-slate-500">From</dt>
          <dd className="font-medium break-all text-slate-800">{item.sender_email}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Format</dt>
          <dd className="font-medium text-slate-800">{item.email_format === "HTML" ? "HTML" : "Plain text"}</dd>
        </div>
        <div>
          <dt className="text-slate-500">CC</dt>
          <dd className="font-medium break-all text-slate-800">{item.cc.join(", ") || "—"}</dd>
        </div>
        <div>
          <dt className="text-slate-500">BCC</dt>
          <dd className="font-medium break-all text-slate-800">{item.bcc.join(", ") || "—"}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Attempts</dt>
          <dd className="font-medium text-slate-800">{item.attempts}</dd>
        </div>
        {item.error_message && (
          <div className="col-span-2 sm:col-span-3">
            <dt className="text-slate-500">{item.status === "FAILED" ? "Failure reason" : "Last error (will retry)"}</dt>
            <dd className="font-medium text-red-700">{item.error_message}</dd>
          </div>
        )}
      </dl>
      <pre className="max-h-72 overflow-auto rounded-lg border border-slate-200 bg-white px-4 py-3 font-sans text-sm whitespace-pre-wrap text-slate-700">
        {item.body}
      </pre>
    </>
  );
}

export default function HistoryPage() {
  const [data, setData] = useState<EmailHistoryPage | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<EmailStatus | "">("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [noCompany, setNoCompany] = useState(false);
  const [error, setError] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);
  const [accounts, setAccounts] = useState<Record<string, EmailAccount>>({});

  const key = `${page}:${status}`;
  const loading = loadedKey !== key; // derived: true until the current page/filter has loaded

  useEffect(() => {
    let cancelled = false;
    api
      .history(page, PAGE_SIZE, status || undefined)
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError("");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (isMissingCompany(err)) setNoCompany(true);
        else setError(err instanceof ApiError ? err.message : "Could not load history.");
      })
      .finally(() => {
        if (!cancelled) setLoadedKey(`${page}:${status}`);
      });
    return () => {
      cancelled = true;
    };
  }, [page, status, refreshTick]);

  // Account details for the Provider column (history stores the account id).
  useEffect(() => {
    api
      .listEmailAccounts()
      .then((list) => setAccounts(Object.fromEntries(list.map((a) => [a.id, a]))))
      .catch(() => setAccounts({}));
  }, []);

  // While any email on this page is still queued/sending/retrying, refresh every 4 seconds.
  const inFlight = data?.items.some((item) => !FINAL_STATUSES.includes(item.status)) ?? false;
  useEffect(() => {
    if (!inFlight) return;
    const timer = window.setTimeout(() => setRefreshTick((n) => n + 1), 4000);
    return () => window.clearTimeout(timer);
  }, [inFlight, data]);

  const header = (
    <PageHeader title="Email History" description="Every email sent (or attempted) through your email accounts, including account test emails." />
  );

  if (noCompany) {
    return (
      <>
        {header}
        <NeedsCompany />
      </>
    );
  }

  return (
    <>
      {header}
      <Alert kind="error">{error}</Alert>

      <Card>
        <CardHeader
          icon="history"
          title="Email activity"
          meta={data ? `${data.total} email${data.total === 1 ? "" : "s"}` : undefined}
          actions={
            inFlight ? (
              <span className="flex items-center gap-1.5 text-xs font-medium text-blue-600">
                <span className="size-1.5 animate-pulse rounded-full bg-blue-500" /> Live updating
              </span>
            ) : undefined
          }
        />
        <div className="flex gap-1.5 overflow-x-auto border-b border-slate-100 px-5 py-2.5" role="tablist" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button
              key={f.value || "all"}
              type="button"
              role="tab"
              aria-selected={status === f.value}
              onClick={() => {
                setStatus(f.value);
                setPage(1);
              }}
              className={cx(
                "rounded-lg px-3 py-1.5 text-xs font-semibold whitespace-nowrap transition",
                status === f.value ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        {loading && !data ? (
          <LoadingScreen />
        ) : data && data.items.length === 0 ? (
          <EmptyState
            title={status ? "No emails with this status" : "No email history yet"}
            description={status ? "Try another filter." : "Generate or send an email to see activity here."}
            action={
              !status && (
                <Link href="/agent" className={buttonClass("primary", "sm")}>
                  <Icon name="sparkles" className="size-3.5" /> Write one with the AI agent
                </Link>
              )
            }
          />
        ) : (
          data && (
            <>
            <ul className="divide-y divide-slate-100 md:hidden">
              {data.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setExpanded(expanded === item.id ? null : item.id)}
                    aria-expanded={expanded === item.id}
                    className="w-full px-5 py-3 text-left transition hover:bg-slate-50"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 truncate text-sm font-semibold text-slate-800">{item.subject}</p>
                      <div className="flex shrink-0 gap-1">
                        <StatusBadge status={item.status} />
                        {item.is_test && <TestBadge />}
                      </div>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      To {item.recipient} · {item.email_account_id ? providerLabel(accounts[item.email_account_id]) : "Deleted account"}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-400">{formatDate(item.sent_at ?? item.created_at)}</p>
                  </button>
                  {expanded === item.id && (
                    <div className="bg-slate-50/60 px-5 pt-1 pb-4">
                      <EmailDetails item={item} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[640px] table-fixed text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-[11px] font-semibold tracking-wider text-slate-500 uppercase">
                    <th className="w-40 px-5 py-2.5">Recipient</th>
                    <th className="px-3 py-2.5">Subject</th>
                    <th className="hidden w-36 px-3 py-2.5 xl:table-cell">Sender</th>
                    <th className="w-24 px-3 py-2.5">Provider</th>
                    <th className="w-28 px-3 py-2.5">Status</th>
                    <th className="w-36 px-5 py-2.5 text-right">Date</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((item) => (
                    <Fragment key={item.id}>
                      <tr
                        className={cx("cursor-pointer transition hover:bg-slate-50", expanded === item.id && "bg-slate-50")}
                        onClick={() => setExpanded(expanded === item.id ? null : item.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            setExpanded(expanded === item.id ? null : item.id);
                          }
                        }}
                        tabIndex={0}
                        aria-expanded={expanded === item.id}
                      >
                        <td className="truncate px-5 py-3 font-medium text-slate-800">{item.recipient}</td>
                        <td className="truncate px-3 py-3 text-slate-700">{item.subject}</td>
                        <td className="hidden truncate px-3 py-3 text-slate-600 xl:table-cell">{item.sender_name ?? item.sender_email}</td>
                        <td className="truncate px-3 py-3 text-slate-600">
                          {item.email_account_id ? providerLabel(accounts[item.email_account_id]) : "Deleted account"}
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex gap-1">
                            <StatusBadge status={item.status} />
                            {item.is_test && <TestBadge />}
                          </div>
                        </td>
                        <td className="px-5 py-3 text-right text-xs whitespace-nowrap text-slate-500">{formatDate(item.sent_at ?? item.created_at)}</td>
                      </tr>
                      {expanded === item.id && (
                        <tr className="bg-slate-50/60">
                          <td colSpan={6} className="px-5 pt-1 pb-5">
                            <EmailDetails item={item} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          )
        )}

        {data && data.pages > 1 && (
          <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-3">
            <span className="text-xs text-slate-500">
              Page {data.page} of {data.pages}
            </span>
            <div className="flex gap-2">
              <button className={buttonClass("secondary", "sm")} disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <button className={buttonClass("secondary", "sm")} disabled={page >= data.pages || loading} onClick={() => setPage((p) => p + 1)}>
                Next
              </button>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
