"use client";

import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/components/AuthProvider";
import { RequireAuth } from "@/components/RequireAuth";

function UserFooter() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <>
      <div className="user-name">{user.name}</div>
      <div style={{ marginBottom: 8, wordBreak: "break-all" }}>{user.email}</div>
      <button type="button" className="btn-link" onClick={() => logout()}>
        Log out
      </button>
    </>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppShell footer={<UserFooter />}>{children}</AppShell>
    </RequireAuth>
  );
}
