import type { ReactNode } from "react";

import { Icon } from "./Icon";

/** Centered card used by the login and registration pages. */
export function AuthCard({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-white shadow-sm" aria-hidden="true">
            <Icon name="mail" className="size-4.5" />
          </span>
          <span className="text-lg font-bold text-slate-900">Email Agent</span>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{title}</h1>
          <p className="mt-1 mb-5 text-sm text-slate-500">{subtitle}</p>
          {children}
        </div>
        <p className="mt-5 text-center text-sm text-slate-500">{footer}</p>
      </div>
    </div>
  );
}
