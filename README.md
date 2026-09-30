# Email Agent — Profile & Email Configuration Module

A multi-tenant web app where each company stores its profile, connects **its own email accounts**
(SMTP or Gmail OAuth), and uses an **AI email agent** to draft emails grounded in that profile. The
user reviews and edits every draft, then sends it from one of the company's own mailboxes. Every send
is recorded in an email history with its delivery status.

**Stack:** FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · Pydantic v2 · JWT · Celery + Redis ·
Next.js 16 · React 19 · TypeScript · Tailwind CSS v4 · Docker Compose

---

## Features

- **Auth:** register / log in with email + password (bcrypt, JWT). Every company's data is isolated.
- **Company profile:** overview, website, industry, location, services, target customers, value
  propositions, contact details, social links.
- **Email accounts:** several per company. SMTP (Gmail, Outlook or any server; NONE / STARTTLS /
  SSL-TLS) or **Gmail OAuth** (sends through the Gmail API, no mailbox password stored). One default
  account, a per-email account choice, and a **Test** button for each account.
- **Signature & preferences:** reusable signature (auto-append or manual), sender name / reply-to
  overrides, HTML or plain text, daily limit, recipients per email, retry count, default CC/BCC.
- **Templates:** reusable subject/body templates with safe `{{ variable }}` placeholders and preview.
- **AI agent:** drafts a subject and body from the company profile, signature and sender identity
  (optionally following a template). It never sends automatically.
- **Sending:** always from the company's own account, never a shared system sender. Delivery is
  immediate or queued to a Celery worker, with bounded retries.
- **History:** every email and account test, with status (`QUEUED → SENDING → SENT / RETRYING /
  FAILED`), attempts, a safe error message and the account used.

## Architecture

```
Next.js frontend ──JWT──▶ FastAPI /api/v1 ──▶ PostgreSQL (Alembic migrations)
                              │
                              ├──▶ LLM: Groq → Gemini → offline mock
                              ├──▶ SMTP server / Gmail API   (immediate mode)
                              └──▶ Redis ──▶ Celery worker ──▶ SMTP / Gmail API   (background mode)
```

The backend is layered as **endpoints** (HTTP + validation) → **services** (business logic) →
**repositories** (queries always scoped to the caller's company) → **models**. Request and response
schemas are separate, so secrets can be accepted but are never returned.

```
backend/   app/{api,core,models,schemas,repositories,services,worker}, alembic/, tests/
frontend/  src/app (pages), src/components, src/lib (API client)
```

## Quick start (Docker)

Requires Docker Desktop.

```bash
cp .env.example .env    # set POSTGRES_PASSWORD, SECRET_KEY, ENCRYPTION_KEY (commands below)
docker compose --profile mail up --build
```

| Service | URL |
|---|---|
| App | http://localhost:3000 |
| API + Swagger | http://localhost:8000/docs |
| Mailpit (local test inbox) | http://localhost:8025 |

Compose starts PostgreSQL, Redis, the backend (it runs the migrations on start-up), the Celery
worker, the frontend, and Mailpit (`--profile mail`). Stop with `docker compose down`; add `-v` to
also delete the database. To send test emails to Mailpit, set `SMTP_ALLOW_PRIVATE_HOSTS=true` in
`.env` and add an SMTP account with host `mailpit`, port `1025`, security `NONE`.

## Local setup (without Docker)

Prerequisites: Python 3.11+, Node.js 20.19+, PostgreSQL 14+.

```bash
# 1. Databases
psql -U postgres -c "CREATE DATABASE email_agent;"
psql -U postgres -c "CREATE DATABASE email_agent_test;"

# 2. Backend  → http://127.0.0.1:8000
cd backend
python -m venv venv
venv\Scripts\activate             # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # fill in the required values (see below)
alembic upgrade head
uvicorn app.main:app --reload

# 3. Frontend → http://localhost:3000  (second terminal)
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Locally, emails are sent immediately (`EMAIL_DELIVERY_MODE=sync`). For background delivery, start
Redis (`docker compose up -d redis`), set `EMAIL_DELIVERY_MODE=celery`, and run a worker from `backend/`:

```bash
celery -A app.worker.celery_app worker -Q email --loglevel=info --pool=solo   # --pool=solo on Windows
```

## Environment variables

Templates: `backend/.env.example` (local run), `.env.example` (Docker), `frontend/.env.example`.
Real `.env` files are git-ignored.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+psycopg://<user>:<password>@localhost:5432/email_agent` |
| `TEST_DATABASE_URL` | for tests | Separate database whose name ends in `_test` |
| `SECRET_KEY` | yes | JWT signing key: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ENCRYPTION_KEY` | yes (prod) | Fernet key for stored credentials: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ALLOWED_ORIGINS` | yes | Frontend origin(s), e.g. `http://localhost:3000` |
| `LLM_PROVIDER` | | `groq` (default), `gemini` or `mock` |
| `GROQ_API_KEY` / `GROQ_MODEL` | for Groq | Primary LLM (default model `openai/gpt-oss-120b`) |
| `LLM_API_KEY` / `LLM_MODEL` | for Gemini | Secondary LLM (default model `gemini-3.8-flash`) |
| `LLM_FALLBACK_TO_MOCK` | | `true` (default): use the mock if every real provider fails |
| `EMAIL_DELIVERY_MODE` | | `sync` (local default) or `celery` (Docker default) |
| `REDIS_URL` | for celery | Default `redis://localhost:6379/0` |
| `SMTP_ALLOW_PRIVATE_HOSTS` | | Allow private/local SMTP hosts such as Mailpit. Must be `false` in production |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | for Gmail OAuth | Empty values disable Gmail OAuth |
| `FRONTEND_URL` | | Where the browser returns after OAuth (default `http://localhost:3000`) |
| `NEXT_PUBLIC_API_URL` | frontend | Backend URL (public by design; never put secrets here) |

With `ENVIRONMENT=production`, the app refuses to start with unsafe settings (weak `SECRET_KEY`, no
`ENCRYPTION_KEY`, wildcard CORS, private SMTP hosts allowed, non-HTTPS OAuth URLs).

## Email setup

**SMTP account:** *Email Accounts → Add SMTP account*, then press **Test**.

| Provider | Host | Port / security |
|---|---|---|
| Gmail | `smtp.gmail.com` | 587 STARTTLS. Needs 2-Step Verification and an [App Password](https://myaccount.google.com/apppasswords) |
| Outlook / Microsoft 365 | `smtp.office365.com` | 587 STARTTLS. SMTP AUTH must be enabled for the mailbox |
| Mailpit (local) | `localhost` (or `mailpit` in Docker) | 1025, NONE |

**Gmail OAuth (optional):**
1. In Google Cloud Console, enable the **Gmail API**.
2. Configure the OAuth consent screen (External, scopes `openid`, `userinfo.email`, `gmail.send`) and
   add your address as a test user.
3. Create a **Web application** client with the redirect URI
   `http://localhost:8000/api/v1/oauth/gmail/callback`.
4. Put the `GOOGLE_*` values in `backend/.env` (or the root `.env` for Docker) and restart.
5. In the app: *Email Accounts → Connect Gmail (OAuth)*.

## AI email agent

`POST /api/v1/agent/generate-email` builds a context from **only the caller's company** (profile,
services, customers, value propositions, contact details, sender identity, signature, optional
template) and asks the LLM for a subject and body. The draft is returned for review; it is never
sent automatically.

- **Providers:** Groq (primary) → Gemini (secondary) → offline mock (final fallback), behind one
  `LLMProvider` interface. The response reports which provider wrote the draft. Free API keys:
  [Groq](https://console.groq.com/keys), [Gemini](https://aistudio.google.com/apikey).
  With no key configured, the mock is used.
- **Safety:** profile data and instructions are treated as untrusted input. The model is told not to
  invent facts. Output is validated (single-line subject, length limits), and a human reviews every
  draft before sending.

## API documentation

Interactive docs: **http://localhost:8000/docs** (Swagger; click *Authorize* and paste the token from
login), `/redoc`, and `/openapi.json`.

| Area | Endpoints (`/api/v1`) |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Company | `POST / GET / PUT /company` |
| Email accounts | `GET / POST /email-accounts`, `GET / PATCH / DELETE /email-accounts/{id}`, `POST /{id}/set-default`, `POST /{id}/test` |
| Gmail OAuth | `GET /oauth/gmail/authorize`, `GET /oauth/gmail/callback` |
| Signature · Preferences | `/signature` (CRUD) · `GET / PUT /preferences` |
| Templates | `/email-templates` (CRUD), `GET /builtin-variables`, `POST /{id}/preview` |
| AI agent | `POST /agent/generate-email` |
| Sending · History | `POST /emails/send` · `GET /emails/history`, `GET /emails/history/{id}` |
| Health | `GET /` (liveness), `GET /health` (database, plus Redis in celery mode) |

Errors always use the shape `{"error": {"code", "message", "details"}}`.

## Security

- **Passwords:** bcrypt hashes, never returned. Failed logins are rate limited.
- **JWT:** HS256 with the algorithm pinned, required expiry, and a secret from the environment.
- **Isolation:** every query is scoped to the token's company, and no endpoint accepts a company ID.
  Another company's records return 404.
- **Credentials at rest:** SMTP passwords and OAuth tokens are Fernet-encrypted and never appear in
  API responses, logs, email history or the AI context. Logs also pass through a redaction filter.
- **Input:** Pydantic validation on every request. Sender names and subjects must be a single line
  (prevents email header injection). Templates allow only `{{ variable }}` placeholders.
- **SMTP:** TLS certificate verification. With `SMTP_ALLOW_PRIVATE_HOSTS=false`, SMTP hosts must
  resolve to public addresses (prevents SSRF).
- **Other:** ORM-only queries (no SQL injection), explicit CORS origins, security headers,
  Gmail OAuth with single-use state and PKCE. `.env` files are git-ignored.

In production: keep secrets in a secrets manager, serve over HTTPS, and replace the `localStorage`
JWT with HttpOnly cookie sessions.

## Testing

```bash
cd backend && pytest                                         # 427 tests on PostgreSQL (TEST_DATABASE_URL)
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

The backend tests use fakes for SMTP, Google and the LLM, so no real network calls are made. They
cover auth, isolation, accounts, SMTP, OAuth, templates, the AI agent, sending, retries, history,
security and migrations. See [`FINAL_TEST_REPORT.md`](FINAL_TEST_REPORT.md) for the full audit,
including live Docker, retry, outage and browser tests.

## Assumptions

- One user owns one company. Signature and preferences are company-wide.
- Emails are always sent from the selected account's address. Preferences can override only the
  display name and reply-to.
- The daily send limit counts real emails per UTC day. Account test emails are excluded.

## Known limitations

- **Outlook OAuth is not implemented.** Outlook works through SMTP.
- Real Gmail **SMTP** (App Password) delivery was not demonstrated. Gmail OAuth + Gmail API delivery
  was verified for real.
- Gmail OAuth in Google's Testing mode allows only listed test users, and refresh tokens expire after
  7 days.
- Live LLM availability varies (Gemini has returned HTTP 503 under load). The fallback chain keeps
  generation working.
- The JWT is stored in `localStorage` and there are no refresh tokens. Rate limits are in-memory per
  process, and Redis runs without persistence.
- No password reset, email verification, bounce tracking, or automated frontend tests.

## More documentation

- [`ASSIGNMENT_CHECKLIST.md`](ASSIGNMENT_CHECKLIST.md): each requirement with its code location and tests
- [`PROJECT_EXPLANATION.md`](PROJECT_EXPLANATION.md): design walkthrough
- [`FINAL_TEST_REPORT.md`](FINAL_TEST_REPORT.md): test and security audit report
