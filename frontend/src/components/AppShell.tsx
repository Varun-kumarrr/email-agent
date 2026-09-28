"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/company", label: "Company Profile" },
  { href: "/email-accounts", label: "Email Accounts" },
  { href: "/templates", label: "Templates" },
  { href: "/signature", label: "Signature" },
  { href: "/preferences", label: "Preferences" },
  { href: "/agent", label: "AI Email Agent" },
  { href: "/history", label: "Email History" },
];

export function AppShell({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <div className="shell">
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">✉ Email Agent</div>
        <button
          type="button"
          className="btn btn-secondary btn-small menu-toggle"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          Menu
        </button>
        <nav>
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-link ${pathname === item.href ? "active" : ""}`}
              onClick={() => setOpen(false)}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        {footer && <div className="sidebar-footer">{footer}</div>}
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
