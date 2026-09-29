# Project Explanation — Email Agent

A walkthrough of *what* was built and *why*, written for explaining the project in an interview.
File references point to where each idea lives in the code (`backend/app/…` unless stated).

---

## 1. What problem the project solves

Businesses send many similar emails (introductions, follow-ups). Generic AI tools don't know the
company's real offering and invent facts; "send" features often use a shared system mailbox. This
project lets every company store its profile once, connect **its own mailboxes** (SMTP or Gmail
OAuth), generate drafts grounded only in that profile, review/edit them, send them from its real
address — immediately or in the background — and keep a history with delivery status, with each
company's data and credentials isolated from every other company.

## 2. Overall architecture

```
Next.js (browser) ──JWT──▶ FastAPI routers ─▶ services ─▶ repositories / SQLAlchemy ─▶ PostgreSQL
                                   │              │
                                   │              ├─▶ LLM provider (Groq → Gemini → mock)
                                   │              ├─▶ SMTP server / Gmail API   (sync mode)
                                   │              └─▶ Redis queue ─▶ Celery worker ─▶ SMTP / Gmail API
                                   └─ dependencies: DB session, current user, current company, LLM
```

* **Routers** (`api/v1/endpoints/`) handle HTTP only: validation via Pydantic, dependencies,
  status codes.
* **Services** (`services/`) hold business rules: accounts, sending, delivery, OAuth, agent, templates.
* **Repositories** hold company-scoped queries.
* **Worker** (`worker/`) runs the same delivery code as sync mode, from a queue.

## 3. Request flow (example: send an email in background mode)

1. The browser sends `POST /api/v1/emails/send` with `Authorization: Bearer <jwt>`.
2. `get_current_user` validates the JWT; `get_current_company` loads *that user's* company.
3. `EmailSenderService.send` resolves the account (`email_account_id` or the default), applies
   preferences, limits and signature, and saves an `EmailHistory` row as `QUEUED`.
4. The history ID is queued to Redis (`email.send` task); the API returns **202** with the task ID.
5. The Celery worker locks the row, marks it `SENDING`, sends through SMTP or the Gmail API, and
   records `SENT`, `RETRYING` (and re-queues itself) or `FAILED`.
6. The frontend polls `GET /emails/history/{id}` until the status is final.

## 4. Why these technologies

* **FastAPI** — type hints + Pydantic give validation and the OpenAPI/Swagger docs for free;
  `Depends` makes cross-cutting concerns (DB session, current user/company, LLM provider) explicit and
  easy to override in tests. Sync endpoints run in a thread pool, which suits `smtplib`.
* **PostgreSQL** — relational data with integrity: FKs with cascades, unique and **partial unique**
  indexes (one default account per company), row locks (`SELECT … FOR UPDATE`) for delivery, JSON
  columns for flexible lists and settings.
* **SQLAlchemy 2** — typed models; all queries use bound parameters (SQL injection prevented by
  construction); relationships with `delete-orphan` make "replace the services list" an assignment.
* **Alembic** — versioned migrations (`0001`–`0006`), including a data migration (`0002`) that moved
  the single configuration table to multiple accounts without losing data. `create_all()` is not
  used for the application database; tests check the migrations match the models (no drift).
* **Pydantic** — one place for input rules; **separate request and response models**, so a password
  can be accepted but cannot be serialized back; `SecretStr` masks secrets in `repr`.
* **Celery + Redis** — moves slow, failure-prone network delivery out of the HTTP request, with
  scheduled retries. Redis is a simple, fast broker; the database stays the source of truth.

## 5. Authentication

`core/security.py`, `services/auth_service.py`, `api/v1/endpoints/auth.py`

* Register: validate → reject duplicate email (409; the DB unique constraint also catches races) →
  bcrypt hash → store.
* Login: verify bcrypt; unknown email and wrong password return the *same* 401 (a dummy hash check
  keeps timing similar) → issue a JWT `{"sub", "iat", "exp", "type": "access"}` signed with HS256.
* `get_current_user` decodes with the algorithm **pinned** (blocks `alg: none`), requires `exp`/`sub`,
  loads the user; any problem → 401 + `WWW-Authenticate: Bearer`.
* Rate limits on login (per IP + email) and registration (per IP). Stateless tokens; the trade-off
  is no server-side revocation (documented).

## 6. Authorization and company isolation

Authentication answers "who are you?"; authorization answers "what may you access?". Here a user
may access only their own company's data, enforced structurally:

* Every company-owned endpoint depends on `get_current_company`; **no endpoint takes a
  `company_id` or `user_id`** (a test asserts this), and unknown body fields are ignored.
* Records addressed by ID (accounts, templates, history) are looked up with `id AND company_id`;
  another company's ID gives 404, not 403 — no existence leak.
* A selected `email_account_id` is resolved inside the caller's company (404 otherwise) and must be
  active (400 otherwise). Frontend filtering is never relied on.
* The OAuth callback has no JWT, so the user and company come from the server-side one-time state.
* The worker re-checks that the account belongs to the history row's company before sending.

## 7. Database design

* `users 1—1 companies` (unique `companies.user_id`).
* `companies 1—N` `company_services`, `target_customers`, `value_propositions`, `social_links`
  (normalized lists with `position`).
* `companies 1—N email_accounts` — unique `(company_id, account_type, email_address)` and a partial
  unique index on `company_id WHERE is_default`, so the database itself guarantees one default.
* `companies 1—1` `email_signatures`, `email_preferences` (unique FK).
* `companies 1—N email_templates` (name unique per company).
* `companies 1—N email_history`; `email_history.email_account_id → email_accounts` with
  `ON DELETE SET NULL`, so deleting an account keeps the history (sender address is also stored).
* `oauth_states` — hashed one-time OAuth states with the encrypted PKCE verifier and expiry.
* Enum-like columns are VARCHAR validated by SQLAlchemy and Pydantic (no DB CHECK constraint), so new
  values need no migration. UUID keys avoid guessable IDs.

## 8. Email account architecture

One `EmailAccount` table holds both account types (`account_type`: `SMTP` or `OAUTH`;
`provider`: `GMAIL`, `OUTLOOK`, `GENERIC`):

* **SMTP accounts** store host, port, username, security type and a Fernet-encrypted password.
  Gmail / Outlook presets fill in host/port/security.
* **Gmail OAuth accounts** store Fernet-encrypted access and refresh tokens, expiry and scopes — no
  mailbox password.
* Responses expose only `password_configured` / `oauth_connected`.
* **Default account**: the first active account becomes the default; `set-default` moves it; deleting
  or deactivating the default promotes the oldest active account; an inactive account can't be default.
* **Selection**: `email_account_id` on send / generate; omitted → default account. The AI Email Agent
  page's *Send from* picker lists active accounts and sends the chosen ID for both generation and
  sending; the server still enforces ownership and active status.
* Delivery dispatches on the account: SMTP → `smtp_client.send_message`; Gmail OAuth →
  `gmail_delivery.send_via_gmail`. Both raise the same `SmtpSendError(code, message, transient)`, so
  retries, history and the worker are provider-independent.
* The legacy `/email-config` API maps onto the company's primary SMTP account for backward compatibility.

## 9. SMTP flow

`services/smtp_client.py`, `email_account_service.py`, `email_composer.py`

* `SmtpCredentials` is built per send from the **selected account** (password decrypted just in time).
  There is no global SMTP account.
* Security modes: `SSL_TLS` → `smtplib.SMTP_SSL` (usually 465); `STARTTLS` → plain connection upgraded
  with `starttls()` (usually 587); `NONE` → plaintext. TLS verifies certificate and hostname.
* Authentication uses **one** AUTH mechanism (PLAIN, else LOGIN), only if the server advertises AUTH.
  (Trying several mechanisms made Gmail drop the connection; a disconnect during AUTH is classified
  as `auth_failed` and not retried.)
* `classify_error` maps every failure to a **safe** code + message and marks transient errors.
  Gmail/Outlook failures get a provider hint (e.g. "use an App Password").
* SSRF guard: with `SMTP_ALLOW_PRIVATE_HOSTS=false`, hosts resolving to private/loopback/link-local
  addresses are refused. For SMTP, BCC is only in the envelope.

## 10. Gmail OAuth flow

`api/v1/endpoints/oauth.py`, `services/oauth_service.py`, `services/google_oauth.py`

* **Authorize** (JWT required, rate limited): create a state (32 random bytes, stored only as a
  SHA-256 hash, bound to user + company, 10-minute expiry) and a PKCE verifier (stored encrypted);
  return Google's consent URL (scopes `openid email gmail.send`, `access_type=offline`,
  `prompt=consent`, S256 challenge).
* **Callback** (no JWT — Google redirects the browser): consume the state exactly once *before*
  anything else (unknown, expired or reused → error), exchange the code + verifier server-side with the
  client secret, require the `gmail.send` scope and a verified email, then create or update the
  `EmailAccount(OAUTH, GMAIL)` with encrypted tokens. Redirect only to `FRONTEND_URL` with a safe
  `status`/`reason`. The access-log filter redacts the callback query string (authorization code).

## 11. Gmail API flow

`services/gmail_delivery.py`

* **Token refresh**: if the access token expires within 60 s, lock the account row, refresh with the
  refresh token, store the new access token encrypted. After a 401 from Gmail, refresh once and retry.
* **Send**: the same MIME message as SMTP is base64url-encoded and posted to
  `users/me/messages/send`; BCC goes in a header, which Gmail strips before delivery.
* **Errors**: `invalid_grant` (revoked/expired refresh token) → permanent "Reconnect Gmail"; 429/5xx,
  timeouts and network errors → transient (retried); Google error bodies are never passed on.
* Verified for real: a Gmail OAuth account sent a Test email and a background email (API → Redis →
  Celery → Gmail API → `SENT`), with the access token refreshed automatically during the send.

## 12. AI generation

`services/agent/email_agent.py`: load company (+ lists) → sender account (selected or default) →
preferences → signature → optional template → build context → build prompt → provider → output
guard → signature de-duplication → editable draft (subject, body, provider, fallback flag, signature
preview, suggested format/CC/BCC, missing template variables). It never sends email.

**Provider abstraction** (`services/llm/`): `LLMProvider.generate_email()` with three implementations,
all using httpx with an injectable transport for tests and errors mapped to safe `LLMError`s:
`GroqProvider` (primary; Groq's OpenAI-compatible Chat Completions API, model `GROQ_MODEL`, default
`openai/gpt-oss-120b`, JSON mode, key in the `Authorization` header), `GeminiProvider` (secondary; JSON
response schema, key in the `x-goog-api-key` header) and `MockLLMProvider` (deterministic, context-only).
The endpoint receives the provider through the `get_llm` dependency; `get_llm_provider()` builds it from
`LLM_PROVIDER` (`groq`, `gemini` or `mock`), skipping providers without a key.

**Fallback chain**: with `LLM_PROVIDER=groq`, `FallbackLLMProvider` tries Groq, then Gemini, and tags the
email with the provider that wrote it (a Gemini draft is flagged `fallback_used: true` with a warning).
If both fail and `LLM_FALLBACK_TO_MOCK=true`, the agent's existing mock fallback writes the draft;
otherwise 503. The prompt, context and output guard are identical for every provider. In live testing
Gemini first returned HTTP 503 `UNAVAILABLE` (high demand), which the fallback handled; a later live
Gemini request (2026-09-29) succeeded.

## 13. Context construction

`services/agent/context.py`: company overview (name, description, website, industry, location),
services, target customers, value propositions, contact info, social links, sender identity
(effective sender name: preference → account → contact person; sending address; reply-to), signature
text and policy. Only the authenticated company's records; never secrets (tested).

Prompt-injection defences (`prompts.py`, `output_guard.py`): rules-first system prompt that treats
data as untrusted; data as JSON inside delimited blocks; sanitization of control characters and
delimiter look-alikes; output guard (single-line subject, length caps, reject echoes of the rules);
human review before sending.

## 14. Templates

`utils/template_render.py`, `services/template_service.py`: only `{{ variable }}` placeholders — no
expressions or code (unlike passing user text to Jinja or `str.format`), validated on save. Built-in
variables (company name/website, contact person, sender, recipient) are filled automatically; values
are HTML-escaped for HTML templates and made single-line in subjects. In the agent, the rendered
template is given to the model as the structure to follow.

## 15. Sending, Celery, Redis and retries

`services/email_sender.py`, `services/email_delivery.py`, `worker/`

* The send request always creates the history row first (`QUEUED`) — it is the unit of work.
* `EMAIL_DELIVERY_MODE=sync`: `deliver_now` loops attempts inline (short backoff) → 200 or 502.
* `EMAIL_DELIVERY_MODE=celery`: the ID is queued to Redis → 202; if Redis is down the row becomes
  `FAILED` (`queue_unavailable`) and the API returns 503.
* **One attempt** (`attempt_delivery`): lock the row, continue only if `QUEUED`/`RETRYING`, mark
  `SENDING` and increment `attempts`, commit, then send. Duplicate or re-delivered tasks see a
  non-waiting status and do nothing, so an email isn't sent twice (`task_acks_late=False` + row lock).
* **Retry decision**: transient error and `attempts <= max_send_retries` → `RETRYING`; otherwise
  `FAILED`. In the worker the task re-queues itself with
  `min(base × 2^(attempts−1), max) ± 10%` (defaults 30 s / 900 s).
* Real verification: Docker stack with Mailpit (including a retry while Mailpit was paused) and a
  Gmail OAuth account through a local worker with Docker Redis.

## 16. History

`email_history` records every email and account test: account used, sender, reply-to, recipients,
subject, final body, format, status (`QUEUED`/`SENDING`/`RETRYING`/`SENT`/`FAILED`), safe error code
and message, attempts, task id, timestamps and `is_test`. Paginated (≤ 100), filterable by status,
company-scoped; detail returns 404 for other companies. Test emails don't count toward the daily limit.

## 17. Error handling

`core/exceptions.py` defines `AppError` subclasses (400/401/403/404/409/429/502/503) raised by
services; `core/error_handlers.py` converts them and framework errors into
`{"error": {"code", "message", "details"}}`. 422 lists `{field, message}` without echoing input;
integrity errors → 409; database outages → 503; anything else → 500 with a generic message.

## 18. Security decisions

* **Credentials encrypted at rest** (Fernet, `ENCRYPTION_KEY`): SMTP passwords, OAuth tokens, PKCE
  verifiers. Hashing isn't possible because the plaintext is needed to authenticate.
* **Never returned, never logged**: write-only fields, response models without secret fields, a
  log redaction filter, access-log redaction of the OAuth callback, no raw provider responses.
* **Isolation by construction**: no client-supplied company IDs; company-filtered lookups.
* **SSRF guard** for user-supplied SMTP hosts; **header-injection** protection (single-line subjects);
  **safe templates**; **prompt-injection** defences.
* **OAuth**: hashed single-use state, PKCE, server-side exchange, fixed redirect target.
* **CORS** explicit origins; **security headers**; **rate limits** on login, registration, AI and OAuth.
* **Production guard**: refuses weak `SECRET_KEY`, missing `ENCRYPTION_KEY`, wildcard CORS, private
  SMTP hosts, or non-https OAuth/frontend URLs.

## 19. Testing

pytest on a dedicated PostgreSQL database (`email_agent_test`; guarded so it can never touch the
application database), schema built by the real migrations, tables truncated per test. Fakes replace
SMTP (`tests/fakes.py`), Google/Gmail (`tests/fake_google.py`; real Google calls are refused) and the
LLM; Celery runs eagerly. Tests cover every endpoint, isolation, SMTP and Gmail failure matrices,
OAuth state/PKCE, delivery states and retries, templates, prompt injection, secret leakage across full
flows, migrations and an end-to-end workflow.

## 20. Frontend

Next.js 16 App Router + TypeScript: `src/lib/api.ts` is the only backend client (JWT header,
normalized `ApiError`, 401 → logout); `AuthProvider` + `RequireAuth` protect the `(app)` route group;
one page per feature (dashboard checklist, company, email accounts with Connect Gmail, signature,
preferences, templates, AI agent, history with status badges and auto-refresh). React escapes all
output; no raw HTML is rendered.

## 21. Engineering trade-offs

* **One accounts table for SMTP and OAuth** (nullable type-specific columns) instead of two tables:
  simpler queries, one default flag, one FK from history — at the cost of some nullable columns.
* **Database as source of truth for delivery** instead of a Celery result backend: status survives
  worker restarts and is queryable per company.
* **At-most-once hand-off** (`acks_late=False`) + row lock: prefers "never send twice" over "never
  lose a task"; a crashed attempt stays `SENDING` rather than risking a duplicate email.
* **Sync mode kept** as the default for local development: no Redis needed; Docker defaults to Celery.
* **VARCHAR enums without CHECK constraints**: easy to extend; validation lives in the app.
* **In-memory rate limits** and **JWT in `localStorage`**: simple for the assignment; production
  alternatives documented (Redis limits, HttpOnly cookies).
* **Provider chain (Groq → Gemini → mock)**: keeps generation working when a free-tier provider is
  unavailable or rate limited; fallbacks are flagged in the UI. Plain httpx instead of vendor SDKs keeps
  dependencies small and makes the providers easy to fake in tests.

## 22. Production improvements

* Secrets manager + KMS envelope encryption with key rotation.
* HttpOnly cookie sessions with refresh tokens and revocation; password reset + email verification.
* Redis-backed rate limits; Celery monitoring and alerting; bounce/delivery tracking; scheduled sends.
* Outlook / Microsoft 365 OAuth; Google app verification for public Gmail OAuth use.
* CI with tests, lint, type checks, dependency/secret scanning; HTTPS everywhere; SMTP egress rules.
