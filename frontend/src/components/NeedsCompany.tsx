import Link from "next/link";

import { ApiError } from "@/lib/api";

/** True when the API says the company profile has to be created first. */
export function isMissingCompany(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404 && /company profile/i.test(error.message);
}

export function NeedsCompany() {
  return (
    <div className="card">
      <h2>Create your company profile first</h2>
      <p className="muted">This page belongs to your company. Set up the company profile, then come back.</p>
      <Link className="btn" href="/company">
        Go to Company Profile
      </Link>
    </div>
  );
}
