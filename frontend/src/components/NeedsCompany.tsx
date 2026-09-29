import Link from "next/link";

import { ApiError } from "@/lib/api";

import { buttonClass, Card, EmptyState } from "./ui";

/** True when the API says the company profile has to be created first. */
export function isMissingCompany(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404 && /company profile/i.test(error.message);
}

export function NeedsCompany() {
  return (
    <Card>
      <EmptyState
        icon="building"
        title="Create your company profile first"
        description="This page belongs to your company. Set up the company profile, then come back."
        action={
          <Link className={buttonClass("primary")} href="/company">
            Go to Company Profile
          </Link>
        }
      />
    </Card>
  );
}
