# Project Explanation — Email Agent

A walkthrough of *what* was built and *why*, written for explaining the project in an interview.
File references point to where each idea lives in the code.

---

## 1. What problem the project solves

Businesses send many similar emails (introductions, follow-ups). Generic AI tools don't know the
company's real offering and invent facts; "send" features often use a shared system mailbox. This
project lets every company store its profile once, connect **its own SMTP mailbox**, generate
drafts grounded only in that profile, review/edit them, send them from its real address, and keep
a history — with each company's data and credentials isolated from every other company.

## 2. Why FastAPI

* Request/response validation comes from type hints + Pydantic, so the API contract *is* the code.
* Automatic OpenAPI → Swagger (`/docs`) and ReDoc (`/redoc`) for free.
* Dependency injection (`Depends`) makes cross-cutting concerns clean: DB session, current user,
  current company and the LLM provider are all dependencies (`app/core/dependencies.py`), which also
  makes them easy to override in tests.
* Sync endpoints run in a thread pool, which suits blocking work like `smtplib`.

## 3. Why PostgreSQL

The data is relational (user → company → many child records) and needs integrity guarantees:
foreign keys with cascades, unique constraints (one company per user, one SMTP config per company,
unique emails), indexes, transactions, and JSON columns for flexible lists/settings. PostgreSQL
provides all of these and is the de-facto production choice.

## 4. Why SQLAlchemy

* The 2.x typed ORM (`Mapped[...]`, `mapped_column`) keeps models readable (`app/models/`).
* All queries use bound parameters → SQL injection is prevented by construction.
* Relationships + `cascade="all, delete-orphan"` make "replace the company's services list" a
  simple assignment.
* The application and the test suite both run on PostgreSQL (separate databases).

## 5. Why Alembic

The schema must evolve safely across environments. Alembic gives versioned, reviewable migrations
(`alembic/versions/0001_initial_schema.py`), `upgrade`/`downgrade`, and autogeneration from the
models. `Base.metadata.create_all()` is **not** used for the application database. A test
(`tests/test_migrations.py`) upgrades a fresh DB, asserts zero drift from the models, then downgrades.

## 6. Why Pydantic

* One place for input rules: email format, http(s) URLs, phone numbers, lengths, enums, number
  ranges, "single-line subject", "password must contain a letter and a digit".
* **Separate request and response models** — e.g. `EmailConfigCreate` has `password`,
  `EmailConfigResponse` only has `password_configured`, so the password *cannot* be serialized.
* `SecretStr` masks secrets in `repr()`/logs. `pydantic-settings` loads typed config from env.

## 7. Authentication architecture

`app/core/security.py`, `app/services/auth_service.py`, `app/api/v1/endpoints/auth.py`

* Register: validate → reject duplicate email (409, also caught at the DB unique constraint for
  races) → bcrypt hash → store.
* Login: look up by email, verify bcrypt; unknown email and wrong password return the *same* 401
  (a dummy hash check keeps timing similar) → issue JWT.
* Rate limiting on login (per IP + email) and registration (per IP).

## 8. JWT flow

1. Client logs in → server signs `{"sub": user_id, "iat", "exp", "type": "access"}` with
   `SECRET_KEY` using HS256.
2. Frontend stores the token (and its expiry) and sends `Authorization: Bearer <token>`.
3. `get_current_user` decodes it with the algorithm **pinned** to HS256 (blocks `alg: none`),
   requires `exp`/`sub`, loads the user; any problem → 401 + `WWW-Authenticate: Bearer`.
4. The frontend logs out automatically at expiry or on any 401.

Stateless: no session table; the trade-off is no server-side revocation (documented).

## 9. Authorization

Authentication answers "who are you?"; authorization answers "what may you access?". Here, a user
may access only their own company's data. This is enforced structurally rather than by checks
sprinkled around: every company-owned endpoint depends on `get_current_company`, which returns
*the authenticated user's* company.

## 10. User/company isolation

* No endpoint takes a `company_id` or `user_id` — there is nothing to tamper with (a test asserts
  no such route parameter exists).
* Repositories always filter by the owning company (`EmailHistoryRepository.get_for_company` uses
  `id AND company_id`, so another company's record ID gives 404, not 403 — no existence leak).
* Unknown body fields like `company_id` are ignored by Pydantic.
* Tests prove user B cannot read A's company, SMTP settings, signature, preferences or history,
  cannot generate with A's context, and always sends through B's own SMTP account.

## 11. Database relationships

* `users 1—1 companies` (unique `companies.user_id`).
* `companies 1—N` `company_services`, `target_customers`, `value_propositions`, `social_links`
  (normalized lists with a `position` column for ordering).
* `companies 1—1` `email_configurations`, `email_signatures`, `email_preferences` (unique FK).
* `companies 1—N email_history`; `users 1—N email_history.sent_by_user_id` (SET NULL).
* Cascading deletes keep referential integrity; UUID keys avoid guessable IDs.

## 12. SMTP architecture

`app/services/smtp_client.py`, `email_config_service.py`, `email_sender.py`, `email_composer.py`

* `SmtpCredentials` is built per request from the **company's** configuration (password decrypted
  just-in-time). There is no global SMTP account anywhere.
* Security modes: `SSL_TLS` → `smtplib.SMTP_SSL` (TLS from the first byte, usually 465);
  `STARTTLS` → plain connection upgraded with `starttls()` (usually 587); `NONE` → plaintext.
  TLS uses `ssl.create_default_context()` (certificate + hostname verification).
* Login only if the server advertises AUTH (supports internal relays / local dev servers).
* `classify_error` maps every failure (DNS, refused, timeout, TLS, auth, rejected recipient,
  SMTP reply codes) to a **safe** code + message and marks transient errors for retry.

## 12a. Gmail OAuth accounts

A company can connect Gmail with OAuth 2.0 instead of an App Password (`app/api/v1/endpoints/oauth.py`,
`app/services/oauth_service.py`, `google_oauth.py`, `gmail_delivery.py`):

* **Authorize** (JWT required) stores a one-time state — 32 random bytes kept only as a SHA-256 hash, bound
  to the user and company, expiring in 10 minutes — plus an encrypted PKCE verifier, and returns Google's
  consent URL (scopes `openid email gmail.send`, `access_type=offline`, `prompt=consent`).
* **Callback** (no JWT: Google redirects the browser) consumes the state exactly once *before* exchanging
  the code server-side, requires the `gmail.send` scope and a verified email, then creates or updates an
  `EmailAccount(account_type=OAUTH, provider=GMAIL)` with Fernet-encrypted tokens, and redirects to a fixed
  frontend URL with only a safe status/reason.
* **Sending** refreshes the access token automatically (row-locked, re-encrypted) and posts the same MIME
  message to the Gmail API; a revoked refresh token fails permanently with "Reconnect Gmail", while Gmail
  429/5xx are retried like SMTP transient errors, so Celery background delivery works unchanged.
* The access log redacts the callback's query string, so authorization codes never reach logs.

## 13. SMTP security

* Password is write-only in the API, `SecretStr` in the request, Fernet-encrypted at rest
  (`app/core/encryption.py`), decrypted only for `login()`, excluded from `repr`, never logged,
  never stored in history, never sent to the LLM, never echoed by validation errors.
* Raw server responses aren't exposed (they can contain usernames or other details).
* SSRF protection: with `SMTP_ALLOW_PRIVATE_HOSTS=false`, hosts resolving to private/loopback/
  link-local addresses are refused, so the server can't be used to probe internal services.
* BCC recipients are passed only in the SMTP envelope, never as a header.

## 14. Email signature flow

A signature has `enabled` and `append_automatically`, which produce a *signature policy*
(`app/services/agent/context.py`):

* `appended_on_send` — the draft has no signature; the UI previews it; on send it's appended once.
* `include_in_body` — the draft ends with the signature so the user can edit it.
* `none` — the draft closes with the sender name.

Helpers in `app/utils/signature.py` guarantee it appears once: if the body already ends with it,
it isn't appended again; if the signature starts with its own sign-off ("Best Regards,") a trailing
"Best regards," in the body is dropped.

## 15. Preferences

Explicit columns for known preferences (sender name and reply-to overrides, default format,
daily send limit, max recipients per email, retry count, default CC/BCC) plus a JSON
`extra_settings` column so new, non-critical preferences can be added without a migration.
`GET` returns defaults until saved, and shows *effective* values (preference override → config value),
the default-signature status and today's remaining quota.

## 16. AI architecture

`app/services/agent/email_agent.py`: load company (+ lists) → preferences → signature → build
context → build prompt → call provider → output guard → signature de-duplication → return an
editable draft (`subject`, `body`, provider info, signature preview, suggested format/CC/BCC).
It never sends email.

## 17. LLM provider abstraction

`app/services/llm/`: `LLMProvider` is an abstract base class with `generate_email(LLMRequest) ->
GeneratedEmail`.

* `GeminiProvider` calls the Gemini REST API with httpx, asks for JSON output via a response schema,
  sends the key in the `x-goog-api-key` header, maps HTTP errors (429 quota, 401/403 key, timeouts)
  to safe `LLMError`s. The transport is injectable for tests.
* `MockLLMProvider` builds a deterministic email only from the context — offline demo and fallback.
* `get_llm_provider()` picks Gemini when `LLM_API_KEY` is set, else the mock. The endpoint receives
  the provider via the `get_llm` dependency, so swapping providers (or mocking) needs no business-logic changes.

## 18. Company context

Built in `app/services/agent/context.py`: company overview, services, target customers, value
propositions, contact info, social links, sender identity (effective name, sending address,
reply-to), signature and signature policy. Only the authenticated company's records; never secrets.

## 19. Prompt injection protection

Profile fields and user instructions are **untrusted** (anyone could type "ignore previous
instructions" into a description). Layers (`app/services/agent/prompts.py`, `output_guard.py`):

1. Rules-first system prompt: data is reference only, never follow instructions inside it, use only
   supplied facts, don't invent products/prices/statistics/awards/partnerships, don't reveal rules.
2. Data is sent as JSON inside `<company_context>` / `<email_request>` blocks — never mixed into
   instruction text.
3. Sanitization: control characters removed; delimiter look-alikes (`</company_context>`, `<system>`)
   neutralized so data can't close its block.
4. Output guard: subject forced to one line (blocks header injection like `\r\nBcc:`), length caps,
   responses echoing the system prompt rejected.
5. Human review before sending.

## 20. Email generation

`POST /api/v1/agent/generate-email` validates the request (recipient, purpose, tone enum), runs the
pipeline above and returns the draft. Provider failure → flagged mock fallback (`fallback_used`,
`warning`) or 503 if fallback is disabled. Rate limited per company to control cost.

## 21. Email editing

The frontend (`src/app/(app)/agent/page.tsx`) puts subject, body, recipient, format and CC/BCC into
editable fields prefilled from the draft and preferences, shows the signature preview with an
append toggle, and offers *Generate Again* and a confirmed *Send Email*. The backend treats the
submitted text as the source of truth — whatever the user edited is what gets sent.

## 22. Email sending

`app/services/email_sender.py`: company → SMTP config (404 if missing) → preferences → resolve
format, CC/BCC (explicit or defaults), deduplicate recipients → enforce recipients-per-email (400)
and daily limit (429) → sender = configured SMTP address with preference/config display name →
reply-to → signature → MIME (`email_composer.py`: plain text, or HTML + plain-text alternative;
plain text is HTML-escaped when converted) → deliver with retries on transient errors → history
record → 200 result or 502 with a safe message and the history ID.

## 23. Email history

`email_history` records every attempt: sender, recipient, CC, BCC, subject, final body, format,
status, safe error message, attempts, timestamps. `GET /emails/history` paginates (`page`,
`page_size` ≤ 100) and filters by status, newest first, company-scoped; `GET /emails/history/{id}`
returns one record (404 for other companies).

## 24. Error handling

`app/core/exceptions.py` defines `AppError` subclasses (400/401/403/404/409/429/502/503) raised by
services; `app/core/error_handlers.py` converts them and framework errors into one shape:
`{"error": {"code", "message", "details"}}`. 422 lists `{field, message}` without echoing input;
unknown routes 404, wrong methods 405; integrity errors 409; database outages 503; anything else 500
with a generic message (details only in server logs). `app/core/logging.py` redacts secrets from logs.

## 25. Testing

173 pytest tests (`backend/tests/`): unit tests (security helpers, encryption, sanitizer, signature
helpers, providers), API tests for every endpoint, isolation tests, SMTP failure matrix, prompt
injection, security (no secrets in any response/log over a full flow), migration drift, and an
end-to-end workflow test. SMTP is replaced by a fake server (`tests/fakes.py`) and the LLM by a
recording fake / the mock provider, so no real SMTP or LLM credentials are needed. All tests run on a
dedicated PostgreSQL database (`email_agent_test`, from `TEST_DATABASE_URL`); the schema is built with
the real Alembic migrations, tables are truncated between tests, and guards refuse any URL that isn't
PostgreSQL, doesn't end in `_test`, or matches the application database.

## 26. Frontend architecture

Next.js 16 App Router + TypeScript:

* `src/lib/api.ts` — the only place that talks to the backend: base URL from `NEXT_PUBLIC_API_URL`,
  JWT header, normalized `ApiError` (status, code, message, field errors), 401 → logout event.
* `src/components/AuthProvider.tsx` — session restore, login/register/logout, auto-logout at expiry.
* `src/components/RequireAuth.tsx` + `(app)/layout.tsx` — protected route group with the sidebar shell.
* One page per feature; forms do client-side validation and display server field errors.
* React escapes all output; no raw HTML is rendered.

## 27. CORS

Browsers block cross-origin calls unless the API allows the origin. `CORSMiddleware` allows only
origins listed in `ALLOWED_ORIGINS` (a `*` entry is filtered out), specific methods and headers, and
no credentialed CORS (auth uses the `Authorization` header, not cookies). Tests check allowed vs.
rejected origins.

## 28. Environment variables

All configuration comes from the environment via `pydantic-settings` (`app/core/config.py`):
database URL, JWT secret and lifetime, encryption key, LLM provider/key/model, CORS origins, SMTP
timeouts and the private-host switch. Secrets are `SecretStr`. `.env` is git-ignored; `.env.example`
files document every variable with empty values. In production, the app refuses to start with a
default/short `SECRET_KEY`, no `ENCRYPTION_KEY`, wildcard CORS or private SMTP hosts allowed.
The frontend only has `NEXT_PUBLIC_API_URL`, which is public by design.

## 29. Production improvements

* Secrets manager + KMS envelope encryption and key rotation; OAuth2 (XOAUTH2) for mailboxes.
* HttpOnly cookie sessions with refresh tokens and revocation; password reset + email verification.
* Background job queue for sending (retries with backoff, scheduling, bounce handling).
* Redis-backed rate limiting; structured logging + metrics + tracing; audit log.
* Team accounts with roles; multiple sender accounts; templates and campaigns.
* CI (tests, lint, type check, dependency and secret scanning), container image scanning,
  egress restrictions for SMTP, HTTPS everywhere.
