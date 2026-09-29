"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useAuth } from "./AuthProvider";
import { Icon, type IconName } from "./Icon";
import { useWorkspace } from "./Workspace";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function initials(name: string | null | undefined): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : parts[0].slice(0, 2)).toUpperCase();
}

// ----- buttons ---------------------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
type ButtonSize = "sm" | "md";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold whitespace-nowrap transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 disabled:cursor-not-allowed disabled:opacity-60";
const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-blue-600 text-white shadow-sm hover:bg-blue-700 hover:text-white",
  secondary: "border border-slate-300 bg-white text-slate-700 shadow-xs hover:bg-slate-50 hover:text-slate-900",
  danger: "bg-red-600 text-white shadow-sm hover:bg-red-700 hover:text-white",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
};
const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-9.5 px-4 text-sm",
};

/** Class names for buttons and button-styled links. */
export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md", extra?: string): string {
  return cx(BUTTON_BASE, BUTTON_VARIANTS[variant], BUTTON_SIZES[size], extra);
}

export function Spinner({ className = "size-4" }: { className?: string }) {
  return (
    <span
      className={cx("inline-block animate-spin rounded-full border-2 border-current border-r-transparent", className)}
      aria-hidden="true"
    />
  );
}

export function SubmitButton({
  loading,
  children,
  disabled,
  variant = "primary",
  size = "md",
  className,
  type = "submit",
  onClick,
}: {
  loading: boolean;
  children: ReactNode;
  disabled?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  type?: "submit" | "button";
  onClick?: () => void;
}) {
  return (
    <button type={type} className={buttonClass(variant, size, className)} disabled={loading || disabled} onClick={onClick}>
      {loading && <Spinner className="size-3.5" />}
      {children}
    </button>
  );
}

// ----- feedback ----------------------------------------------------------------------------

export function LoadingScreen({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center gap-2.5 text-slate-500" role="status">
      <Spinner className="size-5 text-blue-600" /> {label}
    </div>
  );
}

type AlertKind = "error" | "success" | "info" | "warning";
const ALERT_STYLES: Record<AlertKind, { box: string; icon: IconName }> = {
  error: { box: "border-red-200 bg-red-50 text-red-800", icon: "xCircle" },
  success: { box: "border-emerald-200 bg-emerald-50 text-emerald-800", icon: "checkCircle" },
  info: { box: "border-blue-200 bg-blue-50 text-blue-800", icon: "info" },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-800", icon: "alert" },
};

export function Alert({ kind, children, onDismiss }: { kind: AlertKind; children: ReactNode; onDismiss?: () => void }) {
  if (!children) return null;
  const style = ALERT_STYLES[kind];
  return (
    <div
      className={cx("mb-4 flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm", style.box)}
      role={kind === "error" ? "alert" : "status"}
    >
      <Icon name={style.icon} className="mt-0.5 size-4" />
      <div className="min-w-0 flex-1 whitespace-pre-wrap">{children}</div>
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Dismiss" className="rounded p-0.5 opacity-70 hover:opacity-100">
          <Icon name="close" className="size-4" />
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  icon = "inbox",
  title,
  description,
  action,
}: {
  icon?: IconName;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
      <span className="mb-3 grid size-11 place-items-center rounded-full bg-slate-100 text-slate-500">
        <Icon name={icon} className="size-5" />
      </span>
      <p className="font-semibold text-slate-800">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ----- badges ------------------------------------------------------------------------------

export type BadgeTone = "neutral" | "success" | "danger" | "warning" | "info" | "teal";
const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: "border-slate-200 bg-slate-50 text-slate-600",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  danger: "border-red-200 bg-red-50 text-red-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  info: "border-blue-200 bg-blue-50 text-blue-700",
  teal: "border-teal-200 bg-teal-50 text-teal-700",
};

export function Badge({ tone = "neutral", children, title }: { tone?: BadgeTone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cx("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold whitespace-nowrap", BADGE_TONES[tone])}
    >
      {children}
    </span>
  );
}

const STATUS_STYLE: Record<string, { tone: BadgeTone; label: string }> = {
  QUEUED: { tone: "info", label: "Pending" },
  SENDING: { tone: "info", label: "Sending" },
  RETRYING: { tone: "warning", label: "Retrying" },
  SENT: { tone: "success", label: "Sent" },
  FAILED: { tone: "danger", label: "Failed" },
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLE[status] ?? { tone: "neutral" as BadgeTone, label: status };
  return <Badge tone={style.tone}>{style.label}</Badge>;
}

export function TestBadge() {
  return (
    <Badge tone="neutral" title="Sent by an email account's Test action">
      Test
    </Badge>
  );
}

// ----- layout pieces -------------------------------------------------------------------------

export function Card({ children, className, as: Tag = "div" }: { children: ReactNode; className?: string; as?: "div" | "section" | "form" }) {
  return <Tag className={cx("rounded-xl border border-slate-200 bg-white shadow-sm", className)}>{children}</Tag>;
}

/** Card title row: icon + title (+ small meta text) on the left, actions on the right. */
export function CardHeader({
  icon,
  title,
  meta,
  actions,
  description,
}: {
  icon?: IconName;
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  description?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {icon && <Icon name={icon} className="size-4 text-slate-500" />}
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {meta && <span className="text-xs font-medium text-slate-500">{meta}</span>}
        </div>
        {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  caption,
  captionTone = "muted",
  icon,
  href,
}: {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  captionTone?: "muted" | "success" | "info" | "warning" | "danger";
  icon: IconName;
  href?: string;
}) {
  const toneClass = {
    muted: "text-slate-500",
    success: "text-emerald-600",
    info: "text-blue-600",
    warning: "text-amber-600",
    danger: "text-red-600",
  }[captionTone];
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-semibold tracking-wider text-slate-500 uppercase">{label}</span>
        <span className="hidden size-8 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-600 sm:grid">
          <Icon name={icon} className="size-4" />
        </span>
      </div>
      <div className="mt-1 text-2xl font-bold tracking-tight text-slate-900">{value}</div>
      {caption && <div className={cx("mt-1 text-xs font-medium", toneClass)}>{caption}</div>}
    </>
  );
  const cls = "block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition";
  return href ? (
    <Link href={href} className={cx(cls, "hover:border-blue-200 hover:shadow-md")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

// ----- page header -------------------------------------------------------------------------

function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${user.name}`}
        className="flex items-center gap-2 rounded-full border border-slate-200 bg-white py-1 pr-3 pl-1 shadow-xs transition hover:bg-slate-50"
      >
        <span className="grid size-7 place-items-center rounded-full bg-blue-600 text-xs font-bold text-white">{initials(user.name)}</span>
        <span className="hidden max-w-36 truncate text-sm font-medium text-slate-700 sm:block">{user.name}</span>
        <Icon name="chevronDown" className="size-3.5 text-slate-400" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg">
          <div className="border-b border-slate-100 px-2.5 pt-1.5 pb-2">
            <p className="truncate text-sm font-semibold text-slate-900">{user.name}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
          </div>
          <Link
            role="menuitem"
            href="/settings"
            onClick={() => setOpen(false)}
            className="mt-1 flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900"
          >
            <Icon name="settings" /> Settings
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={() => logout()}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
          >
            <Icon name="logout" /> Log out
          </button>
        </div>
      )}
    </div>
  );
}

export function PageHeader({ title, description }: { title: string; description?: ReactNode }) {
  const workspace = useWorkspace();
  return (
    <header className="mb-6 flex items-start justify-between gap-4 border-b border-slate-200 pb-5">
      <div className="min-w-0">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-slate-500">{description}</p>}
      </div>
      {workspace && (
        <div className="flex shrink-0 items-center gap-2.5">
          {workspace.companyName && (
            <span className="hidden max-w-48 truncate rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-700 sm:block" title="Your company workspace">
              {workspace.companyName}
            </span>
          )}
          <UserMenu />
        </div>
      )}
    </header>
  );
}

// ----- forms -------------------------------------------------------------------------------

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
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-xs font-semibold text-slate-700">
        {label}
      </label>
      {children}
      {hint && !error && <span className="text-xs text-slate-500">{hint}</span>}
      {error && <span className="text-xs font-medium text-red-600">{error}</span>}
    </div>
  );
}

/** Accessible on/off switch backed by a real button with role="switch". */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <div className={cx("flex items-start justify-between gap-4", disabled && "opacity-60")}>
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-800">{label}</p>
        {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cx(
          "relative inline-flex h-5.5 w-10 shrink-0 items-center rounded-full transition disabled:cursor-not-allowed",
          checked ? "bg-blue-600" : "bg-slate-300",
        )}
      >
        <span className={cx("inline-block size-4.5 rounded-full bg-white shadow transition", checked ? "translate-x-5" : "translate-x-0.5")} />
      </button>
    </div>
  );
}
