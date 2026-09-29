"use client";

import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";

interface WorkspaceValue {
  /** The authenticated user's real company name, or null before the profile exists. */
  companyName: string | null;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

/** Loads the current company name for the sidebar and page headers (re-checked on navigation). */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [companyName, setCompanyName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getCompany()
      .then((company) => {
        if (!cancelled) setCompanyName(company.name);
      })
      .catch(() => {
        if (!cancelled) setCompanyName(null);
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return <WorkspaceContext.Provider value={{ companyName }}>{children}</WorkspaceContext.Provider>;
}

/** Null outside the app shell (e.g. on the login page). */
export function useWorkspace(): WorkspaceValue | null {
  return useContext(WorkspaceContext);
}
