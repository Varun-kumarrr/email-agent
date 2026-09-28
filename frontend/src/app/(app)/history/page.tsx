"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";

import { isMissingCompany, NeedsCompany } from "@/components/NeedsCompany";
import { Alert, LoadingScreen, PageHeader } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { EmailHistoryPage, EmailStatus } from "@/lib/types";

const PAGE_SIZE = 10;

export default function HistoryPage() {
  const [data, setData] = useState<EmailHistoryPage | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<EmailStatus | "">("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loadedKey, setLoadedKey] = useState<string | null>(null);
  const [noCompany, setNoCompany] = useState(false);
  const [error, setError] = useState("");

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
  }, [page, status]);

  if (noCompany) {
    return (
      <>
        <PageHeader title="Email History" />
        <NeedsCompany />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Email History" description="Every email sent (or attempted) through your SMTP account." />
      <Alert kind="error">{error}</Alert>

      <div className="card">
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
          <label htmlFor="status" style={{ fontWeight: 600 }}>
            Status
          </label>
          <select
            id="status"
            style={{ width: "auto" }}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as EmailStatus | "");
              setPage(1);
            }}
          >
            <option value="">All</option>
            <option value="SENT">Sent</option>
            <option value="FAILED">Failed</option>
          </select>
          {data && <span className="muted">{data.total} email(s)</span>}
        </div>

        {loading && !data ? (
          <LoadingScreen />
        ) : data && data.items.length === 0 ? (
          <p className="muted">
            No emails yet. <Link href="/agent">Write one with the AI agent</Link>.
          </p>
        ) : (
          data && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Recipient</th>
                    <th>Subject</th>
                    <th>Status</th>
                    <th>Timestamp</th>
                    <th>Sender</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <Fragment key={item.id}>
                      <tr
                        className="clickable"
                        onClick={() => setExpanded(expanded === item.id ? null : item.id)}
                        aria-expanded={expanded === item.id}
                      >
                        <td>{item.recipient}</td>
                        <td>{item.subject}</td>
                        <td>
                          <span className={`badge ${item.status === "SENT" ? "badge-success" : "badge-danger"}`}>
                            {item.status}
                          </span>
                        </td>
                        <td>{new Date(item.sent_at ?? item.created_at).toLocaleString()}</td>
                        <td>{item.sender_name ? `${item.sender_name} <${item.sender_email}>` : item.sender_email}</td>
                      </tr>
                      {expanded === item.id && (
                        <tr>
                          <td colSpan={5}>
                            <div className="grid grid-3" style={{ marginBottom: 10 }}>
                              <div>
                                <div className="muted">Format</div>
                                {item.email_format === "HTML" ? "HTML" : "Plain text"}
                              </div>
                              <div>
                                <div className="muted">CC</div>
                                {item.cc.join(", ") || "—"}
                              </div>
                              <div>
                                <div className="muted">BCC</div>
                                {item.bcc.join(", ") || "—"}
                              </div>
                              <div>
                                <div className="muted">Attempts</div>
                                {item.attempts}
                              </div>
                              {item.error_message && (
                                <div className="span-2">
                                  <div className="muted">Failure reason</div>
                                  {item.error_message}
                                </div>
                              )}
                            </div>
                            <div className="preview">{item.body}</div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}

        {data && data.pages > 1 && (
          <div className="form-actions" style={{ alignItems: "center" }}>
            <button className="btn btn-secondary btn-small" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
              ← Previous
            </button>
            <span className="muted">
              Page {data.page} of {data.pages}
            </span>
            <button
              className="btn btn-secondary btn-small"
              disabled={page >= data.pages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </>
  );
}
