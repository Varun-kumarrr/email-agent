# Email Agent — Profile & Email Configuration Module

A multi-tenant web application where each company stores its profile, connects **its own email
accounts** (SMTP or Gmail OAuth), and uses an **AI email agent** to draft emails grounded in that
profile. The user reviews and edits every draft, then sends it from one of the company's own
mailboxes — immediately or through a Celery background worker. Every send attempt, and every account
test email, is recorded in an email history with its delivery status.

> Backend: Python 3.11 · FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · Pydantic v2 · JWT · Celery · Redis
> Frontend: Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS v4
> Email: SMTP (`smtplib`) · Gmail OAuth 2.0 + Gmail API
> AI: Groq (primary, `openai/gpt-oss-120b`) → Google Gemini (secondary) → offline mock (final fallback), behind one provider interface

---

## Contents

1. [Project overview](#1-project-overview)
2. [Problem statement](#2-problem-statement)
3. [Architecture](#3-architecture)
4. [Tech stack](#4-tech-stack)
5. [Folder structure](#5-folder-structure)
6. [Database](#6-database)
7. [Authentication](#7-authentication)
8. [Authorization & company isolation](#8-authorization--company-isolation)
9. [Company profile](#9-company-profile)
10. [Email accounts (multiple per company)](#10-email-accounts-multiple-per-company)
11. [SMTP accounts](#11-smtp-accounts)
12. [Gmail OAuth accounts & the Gmail API](#12-gmail-oauth-accounts--the-gmail-api)
13. [Email signature](#13-email-signature)
14. [Sending preferences](#14-sending-preferences)
15. [Email templates](#15-email-templates)
16. [AI email generation](#16-ai-email-generation)
17. [LLM providers: Groq, Gemini and the mock fallback](#17-llm-providers-groq-gemini-and-the-mock-fallback)
18. [Email sending & delivery states](#18-email-sending--delivery-states)
19. [Background delivery: Celery + Redis](#19-background-delivery-celery--redis)
20. [Retry behaviour](#20-retry-behaviour)
21. [Email history](#21-email-history)
22. [API documentation (Swagger / OpenAPI)](#22-api-documentation-swagger--openapi)
23. [Local setup](#23-local-setup)
24. [Environment variables](#24-environment-variables)
25. [Alembic migrations](#25-alembic-migrations)
26. [Docker Compose](#26-docker-compose)
27. [Testing](#27-testing)
28. [Security](#28-security)
29. [Production considerations](#29-production-considerations)
30. [Verification status (what was tested for real)](#30-verification-status-what-was-tested-for-real)
31. [Assumptions](#31-assumptions)
32. [Known limitations](#32-known-limitations)
33. [Assignment requirement coverage](#33-assignment-requirement-coverage)
34. [Implemented bonuses](#34-implemented-bonuses)
35. [Demo flow](#35-demo-flow)

---

## 1. Project overview

| Capability | Summary |
|---|---|
| Accounts | Register / log in with email + password; JWT bearer tokens |
| Company profile | Overview, website, industry, location, services/products, target customers, value propositions, contact details, social links |
| Email accounts | Several per company: **SMTP** accounts (host, port, username, app password, NONE / STARTTLS / SSL-TLS) and **Gmail OAuth** accounts. One default account; any active account can be chosen per email |
| Account test | Sends a real test email through the account, reports a safe error on failure, and records the attempt in history (marked as a test) |
| Signature | Reusable signature, enable/disable, append automatically |
| Preferences | Sender name & reply-to overrides, HTML / plain text, daily limit, recipients per email, retry count, default CC/BCC, extensible JSON settings |
| Templates | Reusable subject/body templates with safe `{{ variable }}` placeholders, preview, and use in the AI agent |
| AI agent | Drafts subject + body from the company profile, signature, sender identity and (optionally) a template, with prompt-injection defences. Never sends automatically |
| Sending | From the selected (or default) company account only — no system sender. Immediate (`sync`) or background (`celery`) delivery, with bounded retries |
| History | Every email and account test with status (`QUEUED` / `SENDING` / `RETRYING` / `SENT` / `FAILED`), attempts, safe error, account used |

## 2. Problem statement

Sales and business teams write many similar outreach emails. Generic AI tools don't know the
company's products or positioning and tend to invent facts, and "send" features often go through
a shared system mailbox. This module lets each company:

* describe itself once (the profile becomes the AI's only source of facts),
* connect **its own** mailboxes, so emails come from the company's real addresses,
* generate drafts that reflect its actual offering, review/edit them, and send them,
* keep an auditable history — while keeping every company's data and credentials isolated.

## 3. Architecture

```
┌────────────────────┐  HTTPS + JWT (Authorization: Bearer)  ┌─────────────────────────────────┐
│ Next.js frontend   │ ────────────────────────────────────▶ │ FastAPI  /api/v1                │
│ (App Router, TS)   │ ◀──────────────────────────────────── │  endpoints (HTTP, validation)   │
│ lib/api.ts client  │       JSON  {error:{code,message}}    │  services  (business logic)     │
└────────────────────┘                                        │  repositories (scoped queries)  │
                                                              │  SQLAlchemy models              │
                                                              └──┬─────────┬─────────┬──────┬───┘
                                                                 │         │         │      │
                                                        PostgreSQL   Redis (broker)  │   LLM provider
                                                       (Alembic)        │            │ (Groq → Gemini → mock)
                                                                        ▼            │
                                                            Celery worker ───────────┤
                                                            (background mode)        ▼
                                                                         SMTP server  /  Gmail API
                                                                        (company's own account)
```

Backend layers:

* **api/v1/endpoints** — thin HTTP layer: request/response schemas, dependencies, status codes.
* **core** — settings, security (bcrypt, JWT), Fernet encryption, dependencies
  (`get_current_user`, `get_current_company`, `get_llm`), error handlers, log redaction, rate limits.
* **services** — business logic: company, email accounts, SMTP client, Gmail OAuth + Gmail API,
  signature, preferences, templates, the email agent (context → prompt → provider → output guard),
  email sender and delivery state machine, LLM providers.
* **repositories** — database queries, always filtered by the owning user/company.
* **worker** — the Celery app and the `email.send` task.
* **models / schemas** — SQLAlchemy tables / Pydantic request and response models. They are
  separate so secrets (SMTP password) can be accepted but never returned.

## 4. Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI 0.141, Uvicorn | Type-driven validation, dependency injection, automatic OpenAPI/Swagger |
| Validation | Pydantic v2, pydantic-settings, email-validator | One place for input rules; typed settings from env |
| Database | PostgreSQL (developed on 18), psycopg 3 | FKs, unique/partial indexes, row locks, JSON columns |
| ORM / migrations | SQLAlchemy 2.1, Alembic | Parameterized queries; versioned schema changes |
| Auth | PyJWT (HS256), bcrypt | Stateless bearer tokens; salted adaptive password hashes |
| Secrets at rest | cryptography (Fernet) | Authenticated encryption for SMTP passwords, OAuth tokens and PKCE verifiers |
| Email | `smtplib` + `email`; httpx for the Gmail API | STARTTLS/SSL, MIME multipart; Gmail `users.messages.send` |
| Background jobs | Celery 5.6 + Redis 7 | Queue emails, retry with backoff, keep the HTTP request fast |
| AI | Groq Chat Completions (`openai/gpt-oss-120b`) and Google Gemini REST (`gemini-3.8-flash`) via httpx | Groq primary, Gemini secondary, mock final fallback; JSON output |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS v4 | Routing, type safety, utility-first styling, standalone production build |
| Tests | pytest, FastAPI TestClient, fakes for SMTP / Google / LLM | Run on a dedicated PostgreSQL test database |
| Dev ops | Docker Compose | PostgreSQL, Redis, API, worker, frontend (+ optional Mailpit) |

## 5. Folder structure

```
email-agent/
├── backend/
│   ├── main.py                    # shim: `uvicorn main:app` also works
│   ├── app/
│   │   ├── main.py                # FastAPI app, CORS, security headers, /health, handlers
│   │   ├── api/v1/endpoints/      # auth, company, email_accounts, email_config (legacy), oauth,
│   │   │                          # signature, preferences, templates, agent, emails
│   │   ├── core/                  # config, security, encryption, dependencies, exceptions,
│   │   │                          # error_handlers, logging (redaction), rate_limit
│   │   ├── db/                    # engine/session (database.py), Base + mixins (base.py)
│   │   ├── models/                # user, company (+ child tables), email, template, oauth, enums
│   │   ├── schemas/               # Pydantic request/response models
│   │   ├── repositories/          # user, company, email history queries
│   │   ├── services/
│   │   │   ├── agent/             # context, prompts, output_guard, email_agent
│   │   │   ├── llm/               # base (LLMProvider), groq, gemini, mock, fallback chain, factory
│   │   │   ├── email_account_service.py  # accounts, default rules, provider presets/hints
│   │   │   ├── smtp_client.py     # SMTP connection, SSRF guard, safe error classification
│   │   │   ├── google_oauth.py    # Google endpoints: authorize URL, code exchange, refresh, send
│   │   │   ├── oauth_service.py   # OAuth state + callback handling
│   │   │   ├── gmail_delivery.py  # token refresh + Gmail API delivery
│   │   │   ├── email_sender.py    # send request → history row → sync delivery or Celery queue
│   │   │   ├── email_delivery.py  # delivery state machine (one attempt, row lock, retry decision)
│   │   │   ├── email_composer.py  # MIME building (plain / HTML + text alternative)
│   │   │   └── ...                # company, email_config, signature, preferences, templates, auth
│   │   ├── utils/                 # signature helpers, safe template rendering
│   │   └── worker/                # celery_app.py, tasks.py (email.send)
│   ├── alembic/versions/          # 0001 … 0006
│   ├── tests/                     # pytest suite on PostgreSQL (+ fakes for SMTP, Google, LLM)
│   ├── requirements.txt  pytest.ini  alembic.ini  Dockerfile  .env.example
├── frontend/
│   ├── src/app/(auth)/            # login, register
│   ├── src/app/(app)/             # dashboard, company, email-accounts, email-config (legacy info),
│   │                              # signature, preferences, templates, agent, history, settings (protected)
│   ├── src/components/            # AuthProvider, RequireAuth, AppShell, Workspace, Icon, ListEditor, ui
│   ├── src/lib/                   # api.ts (API client), session.ts, types.ts, emails.ts
│   ├── next.config.ts  Dockerfile  .env.example
├── docker-compose.yml  .env.example
├── README.md  PROJECT_EXPLANATION.md  INTERVIEW_QUESTIONS.md  ASSIGNMENT_CHECKLIST.md
```

## 6. Database

All primary keys are UUIDs; every table has `created_at` / `updated_at`.

```
users 1───1 companies ─┬─< company_services      (name, description, position)
                       ├─< target_customers      (segment, description, position)
                       ├─< value_propositions    (statement, position)
                       ├─< social_links          (platform, url)
                       ├─< email_accounts        (SMTP or OAuth; encrypted credentials; is_default)
                       ├── email_signatures  1:1 (signature_text, enabled, append_automatically)
                       ├── email_preferences 1:1 (format, limits, retries, default cc/bcc, extra_settings JSON)
                       ├─< email_templates       (name, subject/body template, variables, is_active)
                       └─< email_history         (status, attempts, account used, task id, is_test …)
users 1───< email_history.sent_by_user_id   (SET NULL)
email_accounts 1───< email_history.email_account_id (SET NULL: history survives account deletion)
oauth_states                                (hashed one-time OAuth state, PKCE verifier, expiry)
```

| Table | Key constraints |
|---|---|
| `users` | `email` unique + indexed |
| `companies` | `user_id` FK → users (CASCADE), **unique** (one company per user) |
| `company_services`, `target_customers`, `value_propositions`, `social_links` | `company_id` FK (CASCADE), indexed; `social_links` unique `(company_id, url)` |
| `email_accounts` | `company_id` FK (CASCADE); unique `(company_id, account_type, email_address)`; **partial unique index** on `company_id WHERE is_default` → at most one default per company |
| `email_signatures`, `email_preferences` | `company_id` FK (CASCADE), **unique** (one per company) |
| `email_templates` | `company_id` FK (CASCADE); name unique per company |
| `email_history` | `company_id` FK (CASCADE); `email_account_id` FK (SET NULL); composite index `(company_id, created_at)`; index on `status` |
| `oauth_states` | `state_hash` unique; user and company FKs; `expires_at`, `consumed_at` |

Enum-like columns (`security_type`, `provider`, `account_type`, `email_format`, `status`) are stored
as `VARCHAR` without a database CHECK constraint; values are validated by SQLAlchemy
(`validate_strings=True`) and the Pydantic schemas, so adding a value needs no migration. CC/BCC
lists, template variables and `extra_settings` are JSON columns.

Design notes:

* **Contact information lives on `companies`** (contact person, email, phone, address): the
  assignment asks for one primary contact. A `company_contacts` table can be added by migration if
  several contacts are ever needed.
* **Signature and preferences are company-level** (1:1), shared by all of the company's accounts.
* **Email accounts replaced the original single `email_configurations` table** (migration `0002`
  copies existing rows, keeping their IDs, and links history to them).

## 7. Authentication

* `POST /api/v1/auth/register` — `{name, email, password}`; email normalized to lowercase;
  password ≥ 8 chars with a letter and a digit (max 72 bytes — bcrypt's limit); duplicate email → **409**.
* `POST /api/v1/auth/login` — `{email, password}` → `{access_token, token_type, expires_in, user}`.
  Unknown email and wrong password return the same **401** (a dummy hash check keeps timing similar).
* `GET /api/v1/auth/me` — current user (and whether a company profile exists).
* Tokens: HS256, claims `sub` (user id), `iat`, `exp`, `type=access`; algorithm pinned on decode
  (rejects `alg: none`), `exp` required. Missing / invalid / expired / unknown-user tokens → **401**
  with `WWW-Authenticate: Bearer`. Lifetime: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60).
* Passwords hashed with **bcrypt**. Hashes never leave the database.
* Rate limits (429 + `Retry-After`): **failed** logins per IP + email (10 per 5 minutes; successful logins
  are not counted, and once the limit is reached even a correct password is refused until the window
  passes) and registrations per IP.

## 8. Authorization & company isolation

* Every company-owned resource is resolved through `get_current_company` → *the authenticated
  user's* company. **No endpoint accepts a company or user ID** (a test asserts no route has a
  `{company_id}` / `{user_id}` path parameter), and unknown body fields such as `company_id` are ignored.
* Resources addressed by ID (email accounts, templates, history records) are looked up with
  `id AND company_id`; another company's ID returns **404** (no existence leak).
* **Selected email account ownership is checked on the server**: `email_account_id` in a send or
  generate request is resolved within the caller's company; another company's account → 404,
  an inactive account → 400.
* The OAuth callback (which has no JWT) binds to the user and company stored with the one-time state.
* The Celery worker re-checks that the history row's account belongs to the same company before sending.
* Isolation tests cover company profile, email accounts, legacy config, signature, preferences,
  templates, history, AI context and sending.

## 9. Company profile

`POST /api/v1/company` (create; 409 if one exists) · `GET /api/v1/company` · `PUT /api/v1/company`
(replace, lists included).

Validation: required name and description; lengths capped; emails validated; URLs must be http(s)
(`www.example.com` is normalized to `https://www.example.com/`); phone format checked; up to 50
items per list.

```json
POST /api/v1/company
{
  "name": "ABC Technologies",
  "description": "AI-powered CRM solutions for small and medium-sized businesses.",
  "website": "www.abctech.com",
  "industry": "Software",
  "location": "Bengaluru, India",
  "contact_person": "Anjali Sharma",
  "contact_email": "anjali@abctech.com",
  "contact_phone": "+91 98765 43210",
  "address": "12 MG Road, Bengaluru",
  "services": [{"name": "CRM"}, {"name": "Sales automation"}],
  "target_customers": [{"segment": "Small and medium-sized businesses"}],
  "value_propositions": [{"statement": "Reduce manual sales work and improve productivity."}],
  "social_links": [{"platform": "LinkedIn", "url": "https://www.linkedin.com/company/abctech"}]
}
```

## 10. Email accounts (multiple per company)

A company can have any number of email accounts. There are two **account types**:

| | SMTP account | Gmail OAuth account |
|---|---|---|
| Created by | `POST /api/v1/email-accounts` (form in the UI) | *Connect Gmail (OAuth)* → Google consent → callback |
| Credential stored | SMTP password / App Password (Fernet-encrypted) | Google access + refresh tokens (Fernet-encrypted) |
| Mailbox password stored? | Yes (encrypted) | **No** — Google issues revocable tokens |
| Sends through | The account's SMTP server (`smtplib`) | Gmail API `users.messages.send` over HTTPS |
| Providers | Gmail, Outlook / Microsoft 365, or any public SMTP server (`provider`: `GMAIL`, `OUTLOOK`, `GENERIC`) | Gmail |
| API shows | `password_configured: true/false` | `oauth_connected: true/false` |

Endpoints (`/api/v1/email-accounts`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/email-accounts` | List the company's accounts |
| POST | `/email-accounts` | Add an SMTP account |
| GET / PATCH / DELETE | `/email-accounts/{id}` | Read, partially update (omit `password` to keep it), delete |
| POST | `/email-accounts/{id}/set-default` | Make it the company default |
| POST | `/email-accounts/{id}/test` | Send a test email through it (`{ "recipient": "…" }`) |

**Default-account rules**

* At most one default per company (enforced by a partial unique index).
* The first **active** account a company adds (SMTP or OAuth) becomes the default automatically.
* `set-default` requires an active account; an inactive account cannot be the default.
* Deleting or deactivating the default promotes the oldest remaining active account.

**Choosing the account for an email.** `POST /emails/send` and `POST /agent/generate-email` accept
an optional `email_account_id`. If it is omitted, the company's default account is used; if it is
given, that account is used after the server checks it belongs to the caller's company (404
otherwise) and is active (400 otherwise). The history record stores the account actually used.

In the UI, the **AI Email Agent** page has a **Send from** selector listing the company's active
accounts (type, provider, sender name, address, default marker — never credentials). Leaving it on
*Default account* sends without `email_account_id` (the default is used); choosing an account sends
its ID for both generation (sender identity) and sending. The review step shows *Sending from …*,
and the send confirmation names the address. With no active account the page shows "No email account
configured. Add an email account before sending." and disables *Send Email*.

**Secrets are never returned by any API**: responses contain only `password_configured` /
`oauth_connected`, never passwords, tokens, or ciphertext.

The legacy single-configuration API (`/api/v1/email-config`, GET/POST/PUT + `/test`) is kept for
backward compatibility; it reads and updates the company's *primary SMTP account*.

## 11. SMTP accounts

```json
POST /api/v1/email-accounts
{
  "account_name": "Sales",
  "provider": "GMAIL",                 // GMAIL | OUTLOOK | GENERIC
  "email_address": "sales@abctech.com",
  "sender_name": "ABC Sales Team",
  "reply_to": "replies@abctech.com",
  "password": "<app password>",
  "is_default": true
}
```

* For `GMAIL` and `OUTLOOK`, host/port/security default to the provider's settings
  (`smtp.gmail.com:587` STARTTLS, `smtp.office365.com:587` STARTTLS) and the username defaults to
  the email address. `GENERIC` requires `smtp_host`, `smtp_port` and `security_type`.
* `security_type`: `NONE` | `STARTTLS` (usually 587) | `SSL_TLS` (usually 465). TLS verifies the
  certificate and hostname (`ssl.create_default_context()`).
* Login uses a **single AUTH mechanism** (PLAIN, else LOGIN) only when the server advertises AUTH.
* Spaces are removed from Gmail App Passwords (Google displays them in groups of four).
* The password is **write-only**: a `SecretStr` in the request, Fernet-encrypted at rest, decrypted
  only at the moment of an SMTP login.
* **SSRF guard**: with `SMTP_ALLOW_PRIVATE_HOSTS=false`, every address the host resolves to must be
  **globally routable** unicast (`ipaddress.is_global`, multicast excluded). Private, loopback,
  link-local, reserved, documentation and shared/CGNAT ranges (100.64.0.0/10, e.g. cloud metadata at
  100.100.100.200) are refused with `host_not_allowed`.
* **Sender names** (accounts, preferences, legacy config) must be a single line: CR, LF and every other
  line-boundary character that email headers reject return 422.

Common settings:

| Provider | Host | Port / security | Notes |
|---|---|---|---|
| Gmail / Google Workspace | `smtp.gmail.com` | 587 STARTTLS or 465 SSL/TLS | Requires 2-Step Verification + a 16-character **App Password** (<https://myaccount.google.com/apppasswords>). Or use Gmail OAuth instead (section 12) |
| Outlook / Microsoft 365 | `smtp.office365.com` | 587 STARTTLS | SMTP AUTH must be enabled for the mailbox |
| Zoho Mail | `smtp.zoho.com` | 465 SSL/TLS or 587 STARTTLS | App-specific password if 2FA |
| Mailtrap (safe testing) | `sandbox.smtp.mailtrap.io` | 587 STARTTLS | Captures emails without delivering them |
| Mailpit (local, Docker) | `localhost:1025` (or `mailpit:1025` inside Compose) | NONE | Needs `SMTP_ALLOW_PRIVATE_HOSTS=true` |

**Account test** — `POST /email-accounts/{id}/test` always returns 200 with `success` and a safe
message, updates `last_tested_at` / `last_test_success`, and records the attempt in history with
`is_test: true`:

```json
{ "success": false, "message": "SMTP authentication failed. Check the username and password (many providers require an app password).", "error_code": "auth_failed", "tested_at": "…" }
```

| error_code | Cause |
|---|---|
| `invalid_host` | DNS lookup failed |
| `connection_refused` | Wrong port / nothing listening |
| `timeout` | Firewall or unreachable host |
| `tls_failed` / `tls_certificate` | Security type doesn't match the port, or bad certificate |
| `auth_failed` | Wrong username / password / App Password (not retried) |
| `recipient_refused`, `sender_refused` | Rejected addresses |
| `feature_unsupported` | e.g. STARTTLS not offered |
| `smtp_error` | Any other SMTP reply (code only, no raw server text) |
| `host_not_allowed` | Host resolves to a non-public address (private, loopback, link-local, CGNAT, …) while `SMTP_ALLOW_PRIVATE_HOSTS=false` |
| `unexpected_error` | Any unclassified failure (e.g. a bug or unreadable stored data): the email is marked `FAILED`, never left `SENDING` |

For Gmail and Outlook, failure messages include a provider-specific hint (e.g. "use an App Password").

## 12. Gmail OAuth accounts & the Gmail API

Besides SMTP, a company can connect a Gmail account with **OAuth 2.0** (authorization code + PKCE).
No mailbox password is stored: the app keeps Google-issued tokens (encrypted) and sends through
the **Gmail API**.

### Google Cloud setup (one time, by the project owner)

1. **Project** — <https://console.cloud.google.com/> → create or select a project.
2. **Enable the Gmail API** — *APIs & Services → Library → "Gmail API" → Enable*.
3. **OAuth consent screen** (*Google Auth Platform → Branding / Audience / Data access*):
   - User type **External** (a personal Gmail account can only use External), app name, support email.
   - **Scopes**: `openid`, `.../auth/userinfo.email` and `https://www.googleapis.com/auth/gmail.send`.
   - **Test users** (Audience): add every Gmail address that will be connected while the app is in *Testing*.
4. **OAuth client** (*Clients → Create client*): type **Web application**; under
   **Authorized redirect URIs** add exactly `http://localhost:8000/api/v1/oauth/gmail/callback`
   (no trailing slash; the same URI works for Docker, which publishes the backend on port 8000).
5. Put the values into **`backend/.env`** (and the root `.env` when using Docker) — never into
   tracked files and never into the frontend:

```
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/oauth/gmail/callback
FRONTEND_URL=http://localhost:3000
```

Restart the backend and the Celery worker (the worker refreshes tokens too). With the ID or secret
empty, `GET /oauth/gmail/authorize` returns 503 and the feature is simply disabled.

### Connection flow

```
Browser ──(JWT) GET /api/v1/oauth/gmail/authorize ──▶ backend
          creates a one-time state (stored as a SHA-256 hash) + PKCE verifier (stored encrypted)
        ◀─ { authorization_url }  (accounts.google.com; scopes openid email gmail.send;
                                   access_type=offline, prompt=consent, S256 code challenge)
Browser ──▶ Google consent screen ──▶ GET /api/v1/oauth/gmail/callback?code=…&state=…   (no JWT)
backend: consume the state exactly once (unknown / expired / reused → error)
       → exchange the code + PKCE verifier for tokens (server-side, with the client secret)
       → require the gmail.send scope and a verified email address
       → create or update EmailAccount(account_type=OAUTH, provider=GMAIL), tokens Fernet-encrypted
       → 302 to FRONTEND_URL/email-accounts?oauth=gmail&status=success | error&reason=<code>
```

In the UI: *Email Accounts → Connect Gmail (OAuth)* → Google's consent screen (in *Testing* mode
Google warns that the app is unverified: choose *Continue*) → tick **Send email on your behalf** →
back on the Email Accounts page with a success or error banner.

### Sending through the Gmail API

1. **Token refresh**: if the access token expires within 60 seconds, it is refreshed with the refresh
   token under a row lock and re-encrypted; after a 401 from Gmail the token is refreshed once and
   the send retried.
2. The same MIME message used for SMTP is base64url-encoded and posted to
   `POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send`. For the Gmail API, BCC
   recipients are passed in a `Bcc` header, which Gmail removes before delivery.
3. A revoked or expired refresh token (`invalid_grant`) fails permanently with a "Reconnect Gmail"
   message (never retried); Gmail 429/5xx, timeouts and network errors are transient and retried.

### Security

* **State**: 32 random bytes, stored only as a SHA-256 hash, bound to the user and company that
  started the flow, expires after `OAUTH_STATE_TTL_SECONDS` (600), consumed once before the code
  exchange. **PKCE (S256)** verifier Fernet-encrypted at rest.
* **Tokens**: access and refresh tokens Fernet-encrypted with `ENCRYPTION_KEY`; API responses
  expose only `oauth_connected`.
* **No leaks**: the client secret, authorization codes and tokens are never logged or returned; the
  Uvicorn access log records the callback as `/callback?[redacted]`; Google error bodies are
  replaced by fixed reason codes.
* **Redirects** go only to the configured `FRONTEND_URL`; the redirect URI sent to Google is the
  configured one.
* The authorize endpoint is rate limited per company. In production, `GOOGLE_REDIRECT_URI` and
  `FRONTEND_URL` must be `https://` (checked at startup).

### Limits of Google's Testing mode

* Only listed **test users** can connect (up to 100); others see "access blocked".
* Google shows an **unverified app** warning; `gmail.send` is a *restricted* scope, so a public
  launch needs Google's app verification.
* **Refresh tokens expire after 7 days** for External apps in Testing: reconnect Gmail when sending
  fails with "Reconnect Gmail".

## 13. Email signature

`POST | GET | PUT | DELETE /api/v1/signature` — `{signature_text, enabled, append_automatically}`.

| Signature state | AI draft | On send |
|---|---|---|
| enabled + append automatically | Draft has no signature; UI shows a preview | Appended once (not duplicated; a duplicate sign-off such as "Best regards," is removed) |
| enabled, manual | Draft ends with the signature so it can be edited | Not appended (unless `append_signature: true`) |
| disabled / none | Draft ends with the sender name | Not appended |

## 14. Sending preferences

`GET /api/v1/preferences` (defaults until saved) · `PUT /api/v1/preferences`

```json
{
  "sender_name": "ABC Sales Team",     // overrides the account's sender name (null = use account)
  "reply_to": "sales@abctech.com",     // overrides the account's reply-to
  "default_format": "HTML",            // HTML | PLAIN_TEXT
  "daily_send_limit": 100,             // 1–10000 per UTC day
  "max_recipients_per_email": 10,      // To + CC + BCC, 1–50
  "max_send_retries": 2,               // 0–5 retries of transient failures
  "default_cc": ["manager@abctech.com"],
  "default_bcc": [],
  "extra_settings": {}                 // JSON: future preferences without a migration
}
```

The response adds `effective_sender_name`, `effective_reply_to`, a `signature` summary,
`sent_today` and `remaining_today`. The daily limit counts real emails that are queued, in progress
or sent (so background queueing cannot exceed it); account test emails are not counted.

## 15. Email templates

`/api/v1/email-templates`: list (`?active_only=true`), create, get, `PATCH`, delete,
`GET /builtin-variables`, and `POST /{id}/preview`.

* A template has a name (unique per company), description, category, subject and body templates,
  content type (plain text or HTML), declared variables and an active flag.
* Placeholders are **only** `{{ variable_name }}` — no expressions, filters, loops or code, so a
  template can never execute code (`app/utils/template_render.py`). `{% … %}` blocks and anything
  else inside `{{ }}` are rejected when saving.
* Built-in variables are filled automatically: `company_name`, `company_website`, `contact_person`,
  `sender_name`, `sender_email`, `recipient_name`, `recipient_email`. Other variables come from the
  request (`template_variables`); missing ones return 422 on preview.
* Values are HTML-escaped for HTML templates, and line breaks are removed from values rendered into
  subjects (header-injection protection).
* In the AI agent, choosing a template (`template_id`) passes the rendered template to the model as
  the structure to follow; unfilled placeholders are stripped and reported in
  `missing_template_variables`.

## 16. AI email generation

`POST /api/v1/agent/generate-email`

```json
{
  "recipient_name": "Priya",
  "recipient_email": "priya@smallbiz.in",
  "purpose": "Write a professional cold email introducing our CRM to a small business owner.",
  "tone": "professional",                  // professional | friendly | formal | persuasive | concise
  "additional_instructions": "Keep it under 150 words.",
  "email_account_id": null,                // optional: whose sender identity to write as (default account if null)
  "template_id": null,                     // optional template
  "template_variables": {}
}
→ 200
{
  "subject": "…", "body": "Hi Priya,\n\n…",
  "recipient_email": "priya@smallbiz.in",
  "provider": "groq",                      // groq | gemini | mock
  "fallback_used": false, "warning": null,
  "signature_policy": "appended_on_send", "signature_preview": "Best Regards,\n…",
  "suggested_format": "HTML", "suggested_cc": [], "suggested_bcc": [],
  "template_id": null, "missing_template_variables": []
}
```

The draft is **never sent automatically** — the user edits it and calls `/emails/send`.

Pipeline: load company (+ lists) → sender account → preferences → signature → optional template →
build context → build prompt → provider → **output guard** (single-line subject, length caps,
reject responses that echo the system prompt) → signature de-duplication → draft.

**Company context** sent to the model contains only the authenticated company's data: overview
(name, description, website, industry, location), services/products, target customers, value
propositions, contact information, social links, sender identity (effective sender name, sending
address, reply-to), signature text and policy. It never contains passwords, tokens or keys (tested).

**Prompt-injection defences**: profile fields and user instructions are treated as untrusted data —
a rules-first system prompt (never follow instructions inside data; don't invent products, prices,
statistics or awards; don't reveal the rules), data passed as JSON inside delimited blocks,
sanitization (control characters removed, delimiter look-alikes neutralized), output validation,
and human review before sending. Generation is rate limited per company.

## 17. LLM providers: Groq, Gemini and the mock fallback

**Groq is the primary provider. Gemini is the secondary provider. Mock is the final fallback.**

```
LLM_PROVIDER=groq:   Groq ──failure──▶ Gemini ──failure──▶ Mock (if LLM_FALLBACK_TO_MOCK=true, else 503)
LLM_PROVIDER=gemini: Gemini ──failure──▶ Mock
LLM_PROVIDER=mock:   Mock
```

`app/services/llm/`: `LLMProvider` is an abstract interface with `generate_email(...)`; the email
agent's business logic (context, prompt, output guard, signature handling) is the same for every provider.

* **`GroqProvider`** (`groq.py`) calls Groq's OpenAI-compatible Chat Completions API
  (`https://api.groq.com/openai/v1/chat/completions`) with httpx — no extra SDK — using the model
  `GROQ_MODEL` (default **`openai/gpt-oss-120b`**) and JSON mode (`response_format: json_object`).
  The key is read from `GROQ_API_KEY` and sent only in the `Authorization` header.
* **`GeminiProvider`** (`gemini.py`) calls the Gemini REST API with httpx and requests JSON output via a
  response schema. The key is read from `LLM_API_KEY` and sent in the `x-goog-api-key` header (not the URL).
* **`FallbackLLMProvider`** (`fallback.py`) tries real providers in order (Groq, then Gemini) and tags the
  email with the provider that wrote it. Each failure is logged as `LLM provider <name> failed code=<code>`
  — never with keys, headers or provider error bodies.
* **`MockLLMProvider`** builds a deterministic email only from the company context (and template, if
  any) — used when no key is configured, and as the final fallback.
* A provider whose API key is empty is skipped (no key at all → mock). HTTP errors (429 rate limit,
  401/403 key, 5xx, timeouts, malformed output) become safe `LLMError`s.
* The response reports `provider` (`groq`, `gemini` or `mock`). `fallback_used: true` with a `warning`
  (shown in the UI) means the primary provider failed and Gemini or the mock wrote the draft. With
  `LLM_FALLBACK_TO_MOCK=false`, the API returns 503 when every real provider fails.

Configure Groq (primary):

1. Create an API key in the Groq console: <https://console.groq.com/keys>.
2. In `backend/.env` (git-ignored — never commit API keys):

```
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=openai/gpt-oss-120b
```

Configure Gemini (secondary, optional): create a key at <https://aistudio.google.com/apikey> and set
`LLM_API_KEY=your-gemini-api-key` and `LLM_MODEL=gemini-3.8-flash`. Keep `LLM_FALLBACK_TO_MOCK=true`.

Restart the backend after changing keys (settings are read at startup). For Docker, put the same
variables in the root `.env`.

**Test email generation**: open *AI Email Agent*, fill in a recipient and purpose, click *Generate Email*
and check the provider badge (`groq`, or `gemini` / `mock` with a fallback warning); or call
`POST /api/v1/agent/generate-email` in Swagger and look at `provider` and `fallback_used`.

Availability of live providers can vary, and free/developer rate limits apply to both Groq
(<https://console.groq.com/docs/rate-limits>) and Gemini
(<https://ai.google.dev/gemini-api/docs/rate-limits>); the fallback chain keeps generation working. To
add another provider, implement `LLMProvider` and add it in `app/services/llm/__init__.py`.

**Live Groq status.** A live generation through `POST /api/v1/agent/generate-email` (2026-09-29, model
`openai/gpt-oss-120b`, fictional demo company) **succeeded** in about 2 seconds: the response reported
`provider: groq` and `fallback_used: false`, and the draft used the company's services and the requested
call. The API key did not appear in the response or the logs. Availability and rate limits can change.

**Live Gemini status (honest result).** Earlier real requests with a valid free-tier key reached the
Gemini API (key accepted, model found) but returned **HTTP 503 `UNAVAILABLE`** — Google's temporary
"model is experiencing high demand" response — for `gemini-3.5-flash-lite` and `gemini-3.8-flash`;
the mock fallback handled those failures as designed. A later live request (2026-09-29, model
`gemini-3.8-flash`, from the AI Email Agent page) **succeeded**: the response reported
`provider: gemini` and `fallback_used: false`, and the draft used the selected account's sender
identity. Free-tier availability varies, so the 503 may recur; the fallback keeps the workflow usable.
The Gemini provider is also covered by automated tests with simulated API responses.

## 18. Email sending & delivery states

`POST /api/v1/emails/send`

```json
{
  "recipient": "priya@smallbiz.in",
  "subject": "Less manual sales work for your business",
  "body": "Hi Priya,\n\n…\n\nBest regards,",
  "format": "HTML",                   // optional: defaults to preferences
  "cc": ["manager@abctech.com"],       // optional: omit = preference defaults, [] = none
  "bcc": [],
  "append_signature": null,           // optional: null = follow signature settings
  "email_account_id": null            // optional: null = company default account
}
```

Flow: company → **selected or default account** (ownership + active checks) → preferences →
format, CC/BCC (explicit or defaults, de-duplicated) → recipients-per-email (400) and daily limit
(429) → sender (`From` = the account's address; display name from preferences or the account) →
reply-to → signature → a history row is saved as **`QUEUED`** → delivery → safe result.

| Mode (`EMAIL_DELIVERY_MODE`) | Behaviour | Response |
|---|---|---|
| `sync` (default in `backend/.env.example`) | Delivered inside the request, transient failures retried inline with a short backoff | **200** with status `SENT`, or **502** `email_send_failed` with a safe message and the history ID |
| `celery` (default in Docker Compose) | The history ID is queued in Redis; the worker delivers it | **202** with status `QUEUED` and `task_id`; **503** `queue_unavailable` if Redis is unreachable (the row is marked `FAILED`); bounded by a 2 s connect / 5 s read timeout and one publish retry (measured in Docker: ~4 s with the Redis container stopped — Docker's DNS takes ~4 s to report a stopped service — and ~5 s with Redis hung) |

Delivery states (`app/services/email_delivery.py`):

```
QUEUED ──▶ SENDING ──▶ SENT
              │
              ├──▶ RETRYING ──▶ SENDING ──▶ …   (transient error, retries left)
              │
              └──▶ FAILED                        (permanent error, or retries exhausted)
```

Each attempt locks the history row (`SELECT … FOR UPDATE`) and proceeds only if it is `QUEUED` or
`RETRYING`, then marks it `SENDING` and increments `attempts` before contacting the provider. A
duplicate or re-delivered task for a row already `SENDING` / `SENT` / `FAILED` does nothing, so an
email is not sent twice.

MIME: plain text, or HTML with a plain-text alternative (plain text is HTML-escaped when converted).
For SMTP, BCC recipients are only in the envelope, never in headers. Subjects must be single-line
(header-injection protection). There is **no hard-coded sender and no global SMTP account**.

## 19. Background delivery: Celery + Redis

```
POST /emails/send ─▶ history row (QUEUED) ─▶ Redis queue "email" ─▶ Celery worker: task email.send
     202 QUEUED                                                       │
                                                                      ├─ SMTP server (SMTP account)
                                                                      └─ Gmail API   (Gmail OAuth account)
                                                                      ▼
                                                  history row: SENDING → SENT / RETRYING / FAILED
```

* Broker: Redis (`CELERY_BROKER_URL`, defaulting to `REDIS_URL`). The database, not a Celery result
  backend, is the source of truth for status (`task_ignore_result=True`).
* Task `email.send(history_id)`; queue `email`; JSON serialization; `worker_prefetch_multiplier=1`;
  time limit 120 s (soft 90 s); `task_acks_late=False` (acknowledged on receipt — combined with the
  row lock this prevents duplicate sends).
* The frontend polls the history record after a queued send until it reaches `SENT` or `FAILED`.

Run a worker locally (from `backend/`, with Redis running):

```bash
celery -A app.worker.celery_app worker --loglevel=info -Q email --pool=solo   # --pool=solo on Windows
```

and set `EMAIL_DELIVERY_MODE=celery` for the backend. Docker Compose starts Redis and the worker for you.

## 20. Retry behaviour

* **Transient** errors are retried: SMTP timeouts, disconnects, refused connections, host names that
  cannot be resolved (a server that is restarting or briefly unreachable) and 4xx replies; Gmail API
  429/5xx, timeouts and network errors. A mistyped host or port therefore fails only after the retries.
* **Permanent** errors are not retried: authentication failures, rejected recipients/senders, 5xx
  SMTP replies, a host blocked by the SSRF guard, unreadable stored credentials, a revoked Gmail refresh
  token, a missing or inactive account, and any unexpected error (`unexpected_error`).
* Every attempt ends in `SENT`, `RETRYING` or `FAILED`; an email is never left in `SENDING` by an error.
* The limit comes from the company's `max_send_retries` preference (0–5): an email gets at most
  `1 + max_send_retries` attempts. `attempts` is recorded on the history row.
* **Background mode**: the task re-queues itself with exponential backoff and jitter:
  `min(EMAIL_RETRY_BASE_SECONDS × 2^(attempts−1), EMAIL_RETRY_MAX_SECONDS) ± 10%`
  (defaults 30 s base, 900 s cap). The row shows `RETRYING` in between.
* **Sync mode**: retries happen inside the request with a short backoff
  (`SMTP_RETRY_BACKOFF_SECONDS × attempts`, default 1 s).

## 21. Email history

`GET /api/v1/emails/history?page=1&page_size=20&status=FAILED` · `GET /api/v1/emails/history/{id}`

Each record stores: the account used (`email_account_id`, null if the account was later deleted),
sender email and name, reply-to, recipient, CC, BCC, subject, final body (with signature), format,
**status**, safe `error_message` and `error_code`, `attempts`, `task_id` (background mode),
`created_at`, `last_attempt_at`, `sent_at` and **`is_test`**.

* **Test-email history**: an account *Test* action creates a record with `is_test: true` (status
  `SENT` or `FAILED`, `attempts: 1`). Test emails are shown with a *Test* badge in the UI and are not
  counted toward the daily sending limit.
* Newest first; page size ≤ 100; filter by status; company-scoped (another company's record → 404).
* History never stores SMTP passwords, OAuth tokens, JWTs, API keys or database credentials.
* The History page filters by status and auto-refreshes while any email is still in progress.

## 22. API documentation (Swagger / OpenAPI)

* Swagger UI: <http://127.0.0.1:8000/docs> (click **Authorize**, paste the `access_token`)
* ReDoc: <http://127.0.0.1:8000/redoc> · OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` · `/health` | – | Liveness (no dependencies) · readiness: database, plus the Redis queue when `EMAIL_DELIVERY_MODE=celery` (503 with `database`/`queue` `unreachable`) |
| POST | `/api/v1/auth/register` · `/api/v1/auth/login` | – | Register · log in → JWT |
| GET | `/api/v1/auth/me` | ✔ | Current user |
| POST / GET / PUT | `/api/v1/company` | ✔ | Company profile |
| GET / POST | `/api/v1/email-accounts` | ✔ | List / add SMTP account |
| GET / PATCH / DELETE | `/api/v1/email-accounts/{id}` | ✔ | One account |
| POST | `/api/v1/email-accounts/{id}/set-default` · `/{id}/test` | ✔ | Default · test email |
| GET | `/api/v1/oauth/gmail/authorize` | ✔ | Start Gmail OAuth → `{authorization_url}` |
| GET | `/api/v1/oauth/gmail/callback` | – (state) | Google redirect target |
| POST / GET / PUT | `/api/v1/email-config` · POST `/email-config/test` | ✔ | Legacy single SMTP config (primary SMTP account) |
| POST / GET / PUT / DELETE | `/api/v1/signature` | ✔ | Signature |
| GET / PUT | `/api/v1/preferences` | ✔ | Sending preferences |
| GET / POST | `/api/v1/email-templates` | ✔ | List / create templates |
| GET | `/api/v1/email-templates/builtin-variables` | ✔ | Built-in variable names |
| GET / PATCH / DELETE | `/api/v1/email-templates/{id}` | ✔ | One template |
| POST | `/api/v1/email-templates/{id}/preview` | ✔ | Render a template |
| POST | `/api/v1/agent/generate-email` | ✔ | AI draft |
| POST | `/api/v1/emails/send` | ✔ | Send (200 sync / 202 queued) |
| GET | `/api/v1/emails/history` · `/history/{id}` | ✔ | History (paginated) · one record |

All errors: `{"error": {"code": "...", "message": "...", "details": ...}}` — codes include
`validation_error` (422, `details: [{field, message}]`, submitted values not echoed),
`unauthorized`, `forbidden`, `not_found`, `conflict`, `rate_limited`, `email_send_failed` (502),
`service_unavailable` (503), `internal_error` (500, generic message only).

## 23. Local setup

Prerequisites: Python 3.11+, Node.js 20.19+ / 22.13+, PostgreSQL 14+ (developed on 18), Git.
Redis is only needed for background mode (Docker Compose provides it).

**1. PostgreSQL** (the only supported database) — create the application and test databases:

```bash
psql -U postgres -h localhost -c "CREATE DATABASE email_agent;"
psql -U postgres -h localhost -c "CREATE DATABASE email_agent_test;"
```

**2. Backend**

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env             # then fill in DATABASE_URL, TEST_DATABASE_URL, SECRET_KEY, ENCRYPTION_KEY …
alembic upgrade head             # create the schema
uvicorn app.main:app --reload    # http://127.0.0.1:8000
```

**3. Frontend**

```bash
cd frontend
npm install
cp .env.example .env.local       # NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
npm run dev                      # http://localhost:3000   (production: npm run build && npm start)
```

**4. Optional — background delivery without Docker for the app**: start Redis
(`docker compose up -d redis`), run the Celery worker (section 19), and start the backend with
`EMAIL_DELIVERY_MODE=celery`.

Open <http://localhost:3000>, register, and follow the dashboard checklist.

## 24. Environment variables

**backend/.env** (template: `backend/.env.example`; `.env` is git-ignored)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✔ | `postgresql+psycopg://user:password@host:5432/email_agent` |
| `TEST_DATABASE_URL` | for tests | Separate PostgreSQL database whose name ends in `_test` |
| `SECRET_KEY` | ✔ | JWT signing key — `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | | Default 60 |
| `ENCRYPTION_KEY` | ✔ in production | Fernet key for SMTP passwords and OAuth tokens — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If empty in development, a key is derived from `SECRET_KEY` |
| `ENVIRONMENT` | | `development` / `production` (production refuses unsafe settings) |
| `LOG_LEVEL`, `SQL_ECHO` | | Default `INFO` / `false` |
| `LLM_PROVIDER` | | `groq` (default: Groq → Gemini → mock), `gemini` or `mock` |
| `GROQ_API_KEY` | for Groq | Groq API key (primary provider); empty → Groq skipped |
| `GROQ_MODEL` | | Default `openai/gpt-oss-120b` |
| `LLM_API_KEY` | for Gemini | Gemini API key (secondary provider); empty → Gemini skipped |
| `LLM_MODEL` | | Default `gemini-3.8-flash` |
| `LLM_TIMEOUT_SECONDS` | | Default 30 |
| `LLM_FALLBACK_TO_MOCK` | | Default `true`: when every real provider fails, return a flagged mock draft instead of 503 |
| `SMTP_TIMEOUT_SECONDS`, `SMTP_RETRY_BACKOFF_SECONDS` | | Defaults 15 / 1 |
| `SMTP_ALLOW_PRIVATE_HOSTS` | | App default `true` (local test servers); must be `false` in production; Compose defaults it to `false` |
| `EMAIL_DELIVERY_MODE` | | `sync` (default) or `celery` |
| `REDIS_URL`, `CELERY_BROKER_URL` | for `celery` | Default `redis://localhost:6379/0`; broker defaults to `REDIS_URL` |
| `EMAIL_RETRY_BASE_SECONDS`, `EMAIL_RETRY_MAX_SECONDS` | | Background retry backoff, defaults 30 / 900 |
| `FRONTEND_URL` | | Where the browser returns after OAuth (default `http://localhost:3000`) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | for Gmail OAuth | Web-application OAuth client; empty disables Gmail OAuth |
| `GOOGLE_REDIRECT_URI` | for Gmail OAuth | Default `http://localhost:8000/api/v1/oauth/gmail/callback`; must match the Google client exactly |
| `OAUTH_STATE_TTL_SECONDS` | | Default 600 |
| `ALLOWED_ORIGINS` | ✔ | Comma-separated frontend origins (no `*`) |

**Root `.env`** (template: `.env.example`) — used only by Docker Compose: `POSTGRES_PASSWORD`,
`SECRET_KEY`, `ENCRYPTION_KEY`, optional LLM, CORS, `EMAIL_DELIVERY_MODE`, `SMTP_ALLOW_PRIVATE_HOSTS`,
Google OAuth and `NEXT_PUBLIC_API_URL` values.

**frontend/.env.local** (template: `frontend/.env.example`): `NEXT_PUBLIC_API_URL` only. It is
public by design — never put secrets in `NEXT_PUBLIC_*` variables.

> Changing `ENCRYPTION_KEY` makes stored SMTP passwords and OAuth tokens unreadable; users would
> need to re-enter passwords / reconnect Gmail (the API says so clearly).

## 25. Alembic migrations

`Base.metadata.create_all()` is not used for the application database; the schema comes only from
Alembic (`backend/alembic/versions/`):

| Revision | Change |
|---|---|
| `0001_initial_schema` | Users, companies and child tables, email configuration, signature, preferences, history |
| `0002_email_accounts` | `email_accounts` (multiple accounts, default flag, OAuth columns); copies existing configurations keeping IDs; adds `email_history.email_account_id` and links history; drops `email_configurations` (downgrade supported) |
| `0003_email_templates` | `email_templates` |
| `0004_email_delivery_status` | Delivery columns on history: `reply_to`, `error_code`, `task_id`, `last_attempt_at` |
| `0005_oauth_states` | `oauth_states` |
| `0006_history_is_test` | `email_history.is_test` (server default `false`) |

```bash
alembic upgrade head      # apply
alembic current           # show revision
alembic downgrade -1      # roll back one
alembic check             # verify the models and migrations match (no drift)
```

The test suite builds its schema with the real migrations and checks for drift; a data-migration
test covers `0002`.

## 26. Docker Compose

```bash
cp .env.example .env                        # set POSTGRES_PASSWORD, SECRET_KEY, ENCRYPTION_KEY (+ optional values)
docker compose up --build                   # db, redis, backend, worker, frontend
docker compose --profile mail up --build    # also Mailpit (local test inbox)
docker compose down                         # stop (add -v only to delete the database volume)
```

| Service | Image / build | Host port | Notes |
|---|---|---|---|
| `db` | `postgres:18` | 5433 → 5432 | Health check `pg_isready`; volume `pgdata` |
| `redis` | `redis:7-alpine` | 6379 | Celery broker; no persistence |
| `backend` | `./backend` | 8000 | Runs `alembic upgrade head`, then Uvicorn as a non-root user; health check `/health` (database + Redis queue) |
| `worker` | `./backend` | – | `celery -A app.worker.celery_app worker -Q email --concurrency=2`; health check `celery inspect ping` |
| `frontend` | `./frontend` (Next.js standalone) | 3000 | `NEXT_PUBLIC_API_URL` is a build argument |
| `mailpit` | `axllent/mailpit` (profile `mail`) | 8025 (web), 1025 (SMTP) | Local SMTP catcher; requires `SMTP_ALLOW_PRIVATE_HOSTS=true` for that session |

* In Compose, `EMAIL_DELIVERY_MODE` defaults to `celery` and `SMTP_ALLOW_PRIVATE_HOSTS` to `false`.
* Docker has its **own** database and reads the **root** `.env`, not `backend/.env`. Gmail OAuth in
  Docker needs the `GOOGLE_*` values in the root `.env`, and accounts must be connected again inside
  the Docker app (tokens encrypted with a different `ENCRYPTION_KEY` cannot be decrypted).

What was run for real with Docker (Docker Desktop 29.8, Compose v5.5): all services built and became
healthy; migrations applied; a background send through Redis + Celery to Mailpit was verified end to
end; retries were verified by pausing Mailpit and by stopping and restarting the Mailpit container
(`RETRYING` → `SENT` on attempt 2, one copy delivered), and a permanent outage ends `FAILED` after the
retry limit. With Redis stopped or hung, `/health` reports `queue: unreachable` and sends return 503. Gmail OAuth was not
configured inside the Docker stack (see section 30).

## 27. Testing

```bash
cd backend
pytest                                    # full suite on PostgreSQL (TEST_DATABASE_URL)
cd ../frontend && npm run lint && npx tsc --noEmit && npm run build
```

* All tests run on a dedicated PostgreSQL database (`email_agent_test`). The suite refuses to start
  unless `TEST_DATABASE_URL` is PostgreSQL, ends in `_test` and differs from `DATABASE_URL`; it
  builds the schema with the real Alembic migrations and truncates tables before each test.
* No real network calls: SMTP is a fake server (`tests/fakes.py`), Google OAuth and the Gmail API
  are a fake transport (`tests/fake_google.py`; real Google requests are refused by an autouse
  fixture), the LLM is a recording fake / the mock provider, and Celery runs eagerly in memory.
* Coverage by area: auth · company · email accounts (defaults, selection, isolation, secrets never
  returned) · legacy config · SMTP (all security modes, failure matrix, single-mechanism AUTH, SSRF
  guard, provider hints) · Gmail OAuth (state, PKCE, callback errors, refresh, Gmail API errors, log
  redaction) · signature · preferences · templates (safe rendering, preview, agent use) · AI (context,
  mock, fallback, prompt injection, output guard) · sending (HTML, plain text, CC/BCC, limits) ·
  background delivery (queueing, retries, duplicate prevention, broker down) · history (test records,
  pagination, isolation) · security (no secrets in responses or logs, SQL-injection payloads, rate
  limits, headers, CORS, production config) · migrations (drift, downgrade, data migration) ·
  an end-to-end workflow.
* Frontend: lint, TypeScript check and production build; no automated UI tests.

## 28. Security

* **Passwords**: bcrypt; never returned; generic login errors; rate-limited login and registration.
* **JWT**: HS256 with pinned algorithm, required `exp`, short lifetime; secret from the environment;
  production refuses a default/short secret.
* **Authorization / isolation**: all data scoped to the token's company; no client-supplied company
  IDs; ID lookups filtered by company (404 otherwise); selected email account ownership verified on
  the server.
* **Credential encryption**: SMTP passwords, OAuth access/refresh tokens and PKCE verifiers are
  Fernet-encrypted at rest with `ENCRYPTION_KEY`; decrypted only when needed; excluded from `repr`.
* **Secrets never in responses**: separate request/response schemas; accounts expose only
  `password_configured` / `oauth_connected`; 422 errors never echo submitted values.
* **Secrets never in logs or history**: nothing logs credentials; a redaction filter additionally
  masks bearer tokens, JWTs, `password=`/`token=`/`api_key=` values, Google and Groq API keys and database
  URL passwords; the OAuth callback query string is redacted from access logs. History and the LLM
  context never contain credentials (tested).
* **SMTP**: TLS with certificate verification; single-mechanism AUTH; raw server replies not
  exposed; SSRF guard against private hosts (`SMTP_ALLOW_PRIVATE_HOSTS=false`).
* **OAuth**: hashed, single-use, expiring, user-bound state; PKCE S256; server-side code exchange;
  fixed redirect target; tokens encrypted; rate-limited authorize endpoint.
* **Validation**: Pydantic for every body (emails, URLs, lengths, enums, ranges); single-line subjects;
  safe template syntax only.
* **SQL injection**: SQLAlchemy ORM with bound parameters only; `hide_parameters=True`.
* **Errors**: consistent JSON errors; no stack traces or raw provider responses returned.
* **CORS**: explicit origins from `ALLOWED_ORIGINS` (`*` filtered out); no credentialed CORS.
* **Security headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on API responses.
* **Rate limits** (in-memory, per process): failed logins, registration, AI generation, OAuth authorize.
* **Frontend**: only `NEXT_PUBLIC_API_URL` is exposed; React escapes output (no raw HTML rendering).
* **Git**: `.env` files ignored; only `.env.example` templates with placeholder values are committed.
* **Production guard**: with `ENVIRONMENT=production` the app refuses to start without a strong
  `SECRET_KEY`, an `ENCRYPTION_KEY`, explicit CORS origins, `SMTP_ALLOW_PRIVATE_HOSTS=false` and
  `https://` OAuth redirect / frontend URLs.

## 29. Production considerations

* **Secrets manager**: keep `SECRET_KEY`, `ENCRYPTION_KEY`, `GROQ_API_KEY`, `LLM_API_KEY`, `GOOGLE_CLIENT_SECRET` and
  the database password in AWS Secrets Manager / GCP Secret Manager / Azure Key Vault / HashiCorp
  Vault and inject them at runtime — not in images or files.
* **KMS envelope encryption** for stored credentials (per-record data keys wrapped by a KMS key),
  with key rotation (`MultiFernet` supports rotation) and re-encryption jobs.
* **Prefer OAuth** (as with Gmail here) over mailbox passwords wherever the provider supports it.
* **HTTPS everywhere** (enforced for OAuth URLs in production mode); TLS to the database; least-
  privilege database user; network isolation; restrict outbound SMTP egress.
* HttpOnly, Secure, SameSite cookie sessions with refresh tokens and revocation instead of
  `localStorage` tokens.
* Redis-backed rate limiting; a Celery result/monitoring stack (e.g. Flower) and alerting;
  structured logging, metrics and tracing; audit log.
* Google app verification before letting users outside the test-user list connect Gmail.

## 30. Verification status (what was tested for real)

| Item | Result |
|---|---|
| Backend automated tests | Pass on PostgreSQL (see section 27) |
| Frontend lint / type check / build | Pass |
| Docker Compose stack | Built and healthy (db, redis, backend, worker, frontend, Mailpit) |
| Background delivery (Redis + Celery) to Mailpit | Verified end to end, including retries after a paused and a stopped/restarted SMTP server, and Redis outages (503, `/health` degraded) |
| **Gmail OAuth connection** | Verified with a real Google account and Google Cloud client (Testing mode) |
| **Gmail API delivery** | Verified: account Test email, and a real background send (API → Redis → Celery worker → Gmail API → `SENT`, 1 attempt, token refreshed automatically) |
| Local SMTP delivery (Mailpit / local SMTP server) | Verified |
| **Real Gmail SMTP delivery** | **Not demonstrated** — a working Gmail App Password was not available (Gmail rejected the configured password); covered by automated tests with a fake SMTP server |
| **Live Groq generation** | Verified (2026-09-29: `provider: groq`, `fallback_used: false`, model `openai/gpt-oss-120b`) |
| **Live Gemini generation** | Verified once (2026-09-29: `provider: gemini`, `fallback_used: false`); earlier attempts returned HTTP 503 `UNAVAILABLE` (high demand), handled by the mock fallback |
| Gmail OAuth inside the Docker stack | Not configured / not tested (verified with the local backend, a local Celery worker and the Docker Redis) |
| Outlook OAuth | Not implemented |

## 31. Assumptions

* One user owns one company (1:1). Multi-user teams per company are a future extension.
* One signature and one preferences record per company, shared by all its email accounts.
* The daily send limit counts real emails per UTC day (queued, in progress or sent); test emails are excluded.
* The sender address is always the selected account's address (providers require it); preferences
  can override the display name and reply-to.

## 32. Known limitations

* **Outlook / Microsoft 365 OAuth is not implemented** (Outlook works through SMTP if the mailbox
  allows SMTP AUTH).
* Real Gmail SMTP delivery was not demonstrated (section 30).
* Live LLM providers can be unavailable or rate limited (Gemini has returned HTTP 503 `UNAVAILABLE` under high demand); drafts then come from the next provider in the chain or the mock (flagged).
* Gmail OAuth in Google's Testing mode: test users only, unverified-app warning, refresh tokens
  expire after 7 days.
* JWT in `localStorage` (XSS-readable); no refresh tokens or server-side revocation; logout is client-side.
* Rate limits are in-memory per process.
* The mock fallback produces a generic, profile-based template; it does not interpret the free-text purpose.
* No password reset or email verification; no bounce/delivery-receipt tracking; no scheduled sends.
* No automated frontend (UI) tests.

## 33. Assignment requirement coverage

See [`ASSIGNMENT_CHECKLIST.md`](ASSIGNMENT_CHECKLIST.md) for the requirement-by-requirement table
with code locations and tests. Summary:

| Area | Where |
|---|---|
| Company profile (all listed fields, create / view / edit) | §9 |
| Email configuration (address, host, port, username, password / App Password, security type, sender name) + test | §10–11 |
| Credential protection + production storage notes | §10, §28, §29 |
| Email signature, auto-available to the agent | §13, §16 |
| Sending preferences (sender, reply-to, signature, auto-append, format, limits, CC/BCC, extensible) | §14 |
| Agent uses company context | §16 |
| Free-tier LLM (Groq primary, Gemini secondary) + configuration + mock fallback | §17 |
| Sends through the user's configured account (no system sender) | §18 |
| FastAPI, PostgreSQL, Pydantic, SQLAlchemy, error handling, env secrets | §3–4, §22, §24 |
| Database design for multiple companies | §6, §25 |
| Authentication + isolation (JWT) | §7–8 |
| Next.js frontend | §5, §23 |
| README, `.env.example`, API docs | this file, §22, §24 |

## 34. Implemented bonuses

| Bonus | Status |
|---|---|
| JWT authentication | Implemented and tested |
| Docker / Docker Compose | Implemented; run for real (section 26) |
| Background processing with Celery + Redis | Implemented; verified end to end (Mailpit and Gmail API) |
| Email sending history / logs | Implemented (incl. delivery status and test-email records) |
| Retry mechanism | Implemented (bounded, exponential backoff in background mode); real retry verified |
| Email templates | Implemented and tested |
| Multiple email accounts per company | Implemented and tested |
| OAuth-based Gmail integration | Implemented; real connection and Gmail API delivery verified |
| OAuth-based Outlook integration | **Not implemented** |
| Secret / encryption management | Fernet encryption for passwords, tokens and PKCE verifiers |
| Unit and integration tests | Implemented (PostgreSQL) |
| Swagger / OpenAPI | `/docs`, `/redoc`, `/openapi.json` |

## 35. Demo flow

1. Open <http://localhost:3000> → **Create account** → you land on **Company Profile**; fill it in
   (e.g. a fictional company, its services, target customers and value propositions) → save.
2. **Email Accounts** → add an SMTP account (e.g. Mailtrap, Mailpit, or Gmail with an App Password)
   and/or **Connect Gmail (OAuth)** → note *Password configured* / *OAuth connected* (secrets are never
   shown) → **Test** an account → mark one as default.
3. **Signature** → *Use example* → enable *Append automatically* → save.
4. **Preferences** → sender name, reply-to, HTML format, default CC, limits, retries → save.
5. **Templates** → create a template with `{{ recipient_name }}` / `{{ company_name }}` → preview.
6. **AI Email Agent** → choose **Send from** (or keep the default account) → recipient, purpose,
   optional template → **Generate Email** → note the draft
   uses only profile facts and shows the provider (`groq`, or `gemini` / `mock` with a fallback warning) → edit →
   **Send Email**.
7. **Email History** → the email appears as `QUEUED` → `SENT` (background mode) or `SENT` / `FAILED`,
   with the account used; account tests carry a *Test* badge.
8. Isolation: log out, register a second user — they see no profile, accounts, templates or history.
9. Swagger at `/docs`: authorize and call `GET /api/v1/email-accounts` — no passwords or tokens.
10. Run `pytest` to show the test suite.
