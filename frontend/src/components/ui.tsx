"use client";

import type { ReactNode } from "react";

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function LoadingScreen({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-screen" role="status">
      <Spinner /> {label}
    </div>
  );
}

type AlertKind = "error" | "success" | "info" | "warning";

export function Alert({ kind, children }: { kind: AlertKind; children: ReactNode }) {
  if (!children) return null;
  return (
    <div className={`alert alert-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function PageHeader({ title, description }: { title: string; description?: ReactNode }) {
  return (
    <div className="page-header">
      <h1>{title}</h1>
      {description && <p>{description}</p>}
    </div>
  );
}

interface FieldProps {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Field({ label, htmlFor, error, hint, className, children }: FieldProps) {
  return (
    <div className={`field ${className ?? ""}`}>
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && !error && <span className="hint">{hint}</span>}
      {error && <span className="error">{error}</span>}
    </div>
  );
}

export function SubmitButton({
  loading,
  children,
  disabled,
  className = "btn",
  type = "submit",
  onClick,
}: {
  loading: boolean;
  children: ReactNode;
  disabled?: boolean;
  className?: string;
  type?: "submit" | "button";
  onClick?: () => void;
}) {
  return (
    <button type={type} className={className} disabled={loading || disabled} onClick={onClick}>
      {loading && <Spinner />}
      {children}
    </button>
  );
}

const STATUS_STYLE: Record<string, { cls: string; label: string }> = {
  QUEUED: { cls: "badge-info", label: "Queued" },
  SENDING: { cls: "badge-info", label: "Sending" },
  RETRYING: { cls: "badge-warning", label: "Retrying" },
  SENT: { cls: "badge-success", label: "Sent" },
  FAILED: { cls: "badge-danger", label: "Failed" },
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLE[status] ?? { cls: "", label: status };
  return <span className={`badge ${style.cls}`}>{style.label}</span>;
}
