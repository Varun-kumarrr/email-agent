"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { useAuth } from "@/components/AuthProvider";
import { AuthCard } from "@/components/AuthCard";
import { Alert, Field, SubmitButton } from "@/components/ui";
import { ApiError } from "@/lib/api";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validate(name: string, email: string, password: string, confirm: string) {
  const errors: Record<string, string> = {};
  if (!name.trim()) errors.name = "Name is required";
  if (!EMAIL_RE.test(email.trim())) errors.email = "Enter a valid email address";
  if (password.length < 8) errors.password = "Use at least 8 characters";
  else if (!/[A-Za-z]/.test(password) || !/\d/.test(password))
    errors.password = "Include at least one letter and one number";
  if (confirm !== password) errors.confirm = "Passwords do not match";
  return errors;
}

export default function RegisterPage() {
  const { register, user, loading } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const justRegistered = useRef(false);

  useEffect(() => {
    // Already logged in when opening this page: go to the dashboard.
    if (!loading && user && !justRegistered.current) router.replace("/dashboard");
  }, [loading, user, router]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const fieldErrors = validate(name, email, password, confirm);
    setErrors(fieldErrors);
    setError("");
    if (Object.keys(fieldErrors).length) return;

    setSubmitting(true);
    justRegistered.current = true;
    try {
      await register(name.trim(), email.trim(), password);
      router.replace("/company"); // next step: create the company profile
    } catch (err) {
      justRegistered.current = false;
      if (err instanceof ApiError) {
        setErrors(err.fieldErrors);
        setError(err.message);
      } else {
        setError("Registration failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const input = (id: string, value: string, set: (v: string) => void, type = "text", autoComplete?: string) => (
    <input
      id={id}
      type={type}
      value={value}
      autoComplete={autoComplete}
      onChange={(e) => set(e.target.value)}
      className={errors[id] ? "invalid" : ""}
    />
  );

  return (
    <AuthCard
      title="Create account"
      subtitle="Set up your company's email agent."
      footer={
        <>
          Already registered? <Link href="/login" className="font-semibold">Log in</Link>
        </>
      }
    >
        <Alert kind="error">{error}</Alert>
        <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          <Field label="Name" htmlFor="name" error={errors.name}>
            {input("name", name, setName, "text", "name")}
          </Field>
          <Field label="Email" htmlFor="email" error={errors.email}>
            {input("email", email, setEmail, "email", "email")}
          </Field>
          <Field label="Password" htmlFor="password" error={errors.password} hint="At least 8 characters, with a letter and a number.">
            {input("password", password, setPassword, "password", "new-password")}
          </Field>
          <Field label="Confirm password" htmlFor="confirm" error={errors.confirm}>
            {input("confirm", confirm, setConfirm, "password", "new-password")}
          </Field>
          <SubmitButton loading={submitting} className="w-full">
            Create account
          </SubmitButton>
        </form>
    </AuthCard>
  );
}
