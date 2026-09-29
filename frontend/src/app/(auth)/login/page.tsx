"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { AuthCard } from "@/components/AuthCard";
import { Alert, Field, LoadingScreen, SubmitButton } from "@/components/ui";
import { ApiError } from "@/lib/api";

/** Only allow redirects to internal paths (prevents open redirects via ?next=). */
function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

function LoginForm() {
  const { login, user, loading: authLoading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!authLoading && user) router.replace(next);
  }, [authLoading, user, router, next]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const fieldErrors: Record<string, string> = {};
    if (!email.trim()) fieldErrors.email = "Email is required";
    if (!password) fieldErrors.password = "Password is required";
    setErrors(fieldErrors);
    setError("");
    if (Object.keys(fieldErrors).length) return;

    setSubmitting(true);
    try {
      await login(email.trim(), password);
      router.replace(next);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setError(err.message);
      } else {
        setError("Login failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Log in"
      subtitle="Welcome back to Email Agent."
      footer={
        <>
          No account? <Link href="/register" className="font-semibold">Create one</Link>
        </>
      }
    >
        {params.get("expired") && <Alert kind="warning">Your session has expired. Please log in again.</Alert>}
        {params.get("registered") && <Alert kind="success">Account created. Please log in.</Alert>}
        <Alert kind="error">{error}</Alert>
        <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          <Field label="Email" htmlFor="email" error={errors.email}>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={errors.email ? "invalid" : ""}
            />
          </Field>
          <Field label="Password" htmlFor="password" error={errors.password}>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={errors.password ? "invalid" : ""}
            />
          </Field>
          <SubmitButton loading={submitting} className="w-full">
            Log in
          </SubmitButton>
        </form>
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <LoginForm />
    </Suspense>
  );
}
