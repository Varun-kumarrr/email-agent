"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAuth } from "./AuthProvider";
import { Icon, type IconName } from "./Icon";
import { cx, initials } from "./ui";
import { useWorkspace, WorkspaceProvider } from "./Workspace";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
  tag?: string;
}

const NAV: { section: string; items: NavItem[] }[] = [
  { section: "Main", items: [{ href: "/dashboard", label: "Dashboard", icon: "dashboard" }] },
  {
    section: "Workspace",
    items: [
      { href: "/company", label: "Company Profile", icon: "building" },
      { href: "/agent", label: "Email Agent", icon: "bot", tag: "AI" },
      { href: "/email-accounts", label: "Email Accounts", icon: "mail" },
      { href: "/templates", label: "Templates", icon: "fileText" },
    ],
  },
  {
    section: "Email",
    items: [
      { href: "/history", label: "Email History", icon: "history" },
      { href: "/signature", label: "Signatures", icon: "pen" },
      { href: "/preferences", label: "Preferences", icon: "sliders" },
    ],
  },
  { section: "System", items: [{ href: "/settings", label: "Settings", icon: "settings" }] },
];

export function BrandMark({ className = "size-8" }: { className?: string }) {
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-lg bg-blue-600 text-white shadow-sm", className)} aria-hidden="true">
      <Icon name="mail" className="size-4" />
    </span>
  );
}

function SidebarItem({ item, active, onNavigate }: { item: NavItem; active: boolean; onNavigate: () => void }) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cx(
        "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition",
        active ? "bg-blue-600 text-white shadow-sm shadow-blue-600/25 hover:text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
      )}
    >
      <Icon name={item.icon} className={cx("size-4", active ? "text-white" : "text-slate-400 group-hover:text-slate-600")} />
      <span className="flex-1 truncate">{item.label}</span>
      {item.tag && (
        <span
          className={cx(
            "rounded-md border px-1.5 text-[10px] font-bold",
            active ? "border-white/40 text-white" : "border-teal-200 bg-teal-50 text-teal-700",
          )}
        >
          {item.tag}
        </span>
      )}
    </Link>
  );
}

function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const workspace = useWorkspace();

  return (
    <aside
      id="app-sidebar"
      aria-label="Main navigation"
      className={cx(
        "fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-slate-200 bg-white transition-transform duration-200 lg:translate-x-0",
        open ? "translate-x-0 shadow-xl" : "-translate-x-full",
      )}
    >
      <div className="flex items-center gap-2.5 px-4 pt-5 pb-4">
        <BrandMark />
        <div className="min-w-0">
          <p className="text-sm font-bold text-slate-900">Email Agent</p>
          <p className="truncate text-xs text-slate-500" title={workspace?.companyName ?? undefined}>
            {workspace?.companyName ?? "No company profile yet"}
          </p>
        </div>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {NAV.map((group) => (
          <div key={group.section}>
            <p className="mb-1.5 px-3 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">{group.section}</p>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <SidebarItem key={item.href} item={item} active={pathname === item.href} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {user && (
        <div className="flex items-center gap-2.5 border-t border-slate-200 px-4 py-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-blue-600 text-xs font-bold text-white" aria-hidden="true">
            {initials(user.name)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-slate-800">{user.name}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
          </div>
          <button
            type="button"
            onClick={() => logout()}
            aria-label="Log out"
            title="Log out"
            className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <Icon name="logout" />
          </button>
        </div>
      )}
    </aside>
  );
}

function ShellContent({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  // The mobile drawer closes with Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="min-h-screen">
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white/95 px-4 py-2.5 backdrop-blur lg:hidden">
        <div className="flex items-center gap-2">
          <BrandMark className="size-7" />
          <span className="text-sm font-bold text-slate-900">Email Agent</span>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          aria-controls="app-sidebar"
          className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
        >
          <Icon name={open ? "close" : "menu"} className="size-5" />
        </button>
      </div>

      <Sidebar open={open} onNavigate={() => setOpen(false)} />
      {open && <div className="fixed inset-0 z-30 bg-slate-900/30 lg:hidden" onClick={() => setOpen(false)} aria-hidden="true" />}

      <main className="lg:pl-60">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-7">{children}</div>
      </main>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <WorkspaceProvider>
      <ShellContent>{children}</ShellContent>
    </WorkspaceProvider>
  );
}
