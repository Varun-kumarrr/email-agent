# Assignment Compliance Checklist

"Tested" means covered by an automated test in `backend/tests/` (run: `cd backend && pytest`,
173 passing on PostgreSQL) and/or verified manually against the running app with PostgreSQL (see the final
system test notes at the bottom). Paths are relative to the repository root.

## Core requirements

| # | Requirement | Implemented | Location | Tested | Notes |
|---|---|---|---|---|---|
| 1 | Company name | Yes | `backend/app/models/company.py`, `schemas/company.py` | Yes — `test_company.py` | Required, 1–200 chars |
| 2 | Company description | Yes | same | Yes — `test_company.py` | Required, ≤5000 chars |
| 3 | Website | Yes | same, `schemas/common.py` (`HttpUrlStr`) | Yes | http(s) only; bare domains normalized |
| 4 | Industry | Yes | same | Yes | Optional |
| 5 | Location | Yes | same | Yes | Optional |
| 6 | Services/products | Yes | `company_services` table | Yes | Normalized child table, ordered |
| 7 | Target customers | Yes | `target_customers` table | Yes | Normalized child table |
| 8 | Value propositions | Yes | `value_propositions` table | Yes | Normalized child table |
| 9 | Contact person | Yes | `companies.contact_person` | Yes | |
| 10 | Contact email | Yes | `companies.contact_email` | Yes | Email validated |
| 11 | Phone | Yes | `companies.contact_phone` | Yes | Format validated |
| 12 | Address | Yes | `companies.address` | Yes | |
| 13 | Social links | Yes | `social_links` table | Yes | URL validated; unique per company |
| 14 | Company CRUD | Yes | `api/v1/endpoints/company.py` (POST/GET/PUT) | Yes | Create/read/update (the required operations); delete not required |
| 15 | Email address | Yes | `models/email.py` `EmailConfiguration.email` | Yes — `test_email_config.py` | |
| 16 | SMTP host | Yes | same | Yes | Hostname validated (no scheme/path) |
| 17 | SMTP port | Yes | same | Yes | 1–65535 |
| 18 | Username | Yes | same | Yes | |
| 19 | Password / app password | Yes | `encrypted_password` column | Yes | Write-only, Fernet-encrypted |
| 20 | Encryption / security type | Yes | `SecurityType` enum (NONE/STARTTLS/SSL_TLS) | Yes — `test_smtp.py` (all three modes) | |
| 21 | Sender name | Yes | `EmailConfiguration.sender_name` (+ preference override) | Yes | Reply-to also supported |
| 22 | SMTP test | Yes | `POST /api/v1/email-config/test`, `services/smtp_client.py` | Yes — `test_smtp.py` (success + 10 failure types) | Verified live with a real SMTP server |
| 23 | Password protection | Yes | separate request/response schemas, `core/encryption.py` | Yes — never in GET/POST/PUT, logs, history, LLM context, 422 errors, OpenAPI | `password_configured` only |
| 24 | Email signature | Yes | `/api/v1/signature` POST/GET/PUT/DELETE | Yes — `test_signature.py` | Enabled flag |
| 25 | Automatic signature | Yes | `append_automatically`, `services/email_sender.py`, `utils/signature.py` | Yes — `test_email_sending.py`, `test_agent_signature.py` | Appended once; duplicate sign-off removed |
| 26 | Sender preferences | Yes | `/api/v1/preferences` | Yes — `test_preferences.py` | Sender name override |
| 27 | Reply-to | Yes | config + preference override | Yes — `Reply-To` header asserted | |
| 28 | Email format | Yes | `default_format` HTML/PLAIN_TEXT, per-send override | Yes — HTML + plain tests | HTML has plain-text alternative |
| 29 | Sending limits/preferences | Yes | `daily_send_limit`, `max_recipients_per_email`, `max_send_retries`, `extra_settings` JSON | Yes — 429/400 tests, retry tests | Extensible JSON column for future prefs |
| 30 | CC | Yes | default CC + per-send CC | Yes | |
| 31 | BCC | Yes | default BCC + per-send BCC | Yes — BCC only in SMTP envelope | |
| 32 | Company context for AI | Yes | `services/agent/context.py` | Yes — `test_agent.py` | |
| 33 | Company overview in AI | Yes | context `company.description` etc. | Yes | |
| 34 | Products in AI | Yes | context `services` | Yes | |
| 35 | Target customers in AI | Yes | context `target_customers` | Yes | |
| 36 | Value proposition in AI | Yes | context `value_propositions` | Yes | |
| 37 | Contact information in AI | Yes | context `contact` | Yes | |
| 38 | Signature in AI | Yes | context `signature`, `signature_policy` | Yes — `test_agent_signature.py` | |
| 39 | Sender identity in AI | Yes | context `sender_name`, `sender_email`, `reply_to` | Yes | Preference overrides applied |
| 40 | Free-tier LLM | Yes | `services/llm/gemini.py` (Google Gemini, `gemini-2.5-flash`) | Yes — mocked HTTP (`test_llm_providers.py`) | Not exercised against the live Gemini API: no key was available during development |
| 41 | LLM configuration documentation | Yes | README §24, `.env.example` | n/a | |
| 42 | Mock / fallback | Yes | `services/llm/mock.py`, fallback in `email_agent.py` | Yes — no-key, failure fallback, 503 when disabled | |
| 43 | User-configured email sending | Yes | `services/email_sender.py` | Yes — `test_email_sending.py`, e2e | Verified live |
| 44 | No hard-coded sender | Yes | From = company's configured SMTP address | Yes — two companies send via their own accounts | No global SMTP settings exist |
| 45 | Python | Yes | Python 3.11 | n/a | |
| 46 | FastAPI | Yes | `backend/app` | Yes | |
| 47 | PostgreSQL | Yes | `DATABASE_URL`, psycopg 3 | Yes — the entire suite runs on PostgreSQL | App DB `email_agent` at head; tests use `email_agent_test` |
| 48 | Pydantic | Yes | `backend/app/schemas`, settings | Yes | |
| 49 | SQLAlchemy | Yes | SQLAlchemy 2.1 typed ORM | Yes | |
| 50 | Error handling | Yes | `core/exceptions.py`, `core/error_handlers.py` | Yes — `test_error_handling.py` | Consistent JSON; 400–503 |
| 51 | Environment variables | Yes | `core/config.py` (pydantic-settings) | Yes — `test_config.py` | |
| 52 | Multi-user support | Yes | `users` table, JWT | Yes | |
| 53 | Multi-company support | Yes | one company per user, all data company-scoped | Yes | |
| 54 | Data isolation | Yes | `get_current_company`, company-filtered repositories | Yes — `test_isolation.py` + per-feature tests + e2e | No company/user IDs accepted from clients |
| 55 | Authentication | Yes | register/login/me | Yes — `test_auth.py` | bcrypt; rate limited |
| 56 | Authorization | Yes | dependency-based company scoping | Yes | 404 for other companies' records |
| 57 | JWT | Yes | `core/security.py` (HS256, exp, pinned alg) | Yes — invalid/expired/forged/alg=none | |
| 58 | Next.js | Yes | `frontend/` (Next.js 16, TypeScript) | Lint + type check + production build; manual browser testing | No automated frontend tests |
| 59 | Input validation | Yes | Pydantic schemas + client-side checks | Yes | |
| 60 | SQL injection protection | Yes | ORM with bound parameters only | Yes — `test_security.py` | |
| 61 | Secure API | Yes | auth, isolation, rate limits, headers, CORS, SSRF guard | Yes — `test_hardening.py`, `test_cors.py` | |
| 62 | No secrets in Git | Yes | `.gitignore`, `.env.example` templates | Verified — history scanned for real secret values | |
| 63 | No secrets in frontend | Yes | only `NEXT_PUBLIC_API_URL` | Verified | |
| 64 | No secrets in logs | Yes | no secret logging + `core/logging.py` redaction | Yes — full-flow log capture test | |
| 65 | README | Yes | `README.md` | n/a | 35 sections |
| 66 | Architecture documentation | Yes | README §3, `PROJECT_EXPLANATION.md` | n/a | |
| 67 | Installation | Yes | README §19–22 | n/a | |
| 68 | Environment variables (docs) | Yes | README §23, three `.env.example` files | n/a | |
| 69 | Database setup | Yes | README §20–21 (Alembic) | n/a | |
| 70 | API documentation | Yes | Swagger `/docs`, ReDoc `/redoc`, README §18 | Yes — `test_api_docs.py` | |
| 71 | Email setup | Yes | README §25 (Gmail, Outlook, Zoho, Mailtrap, local) | n/a | |
| 72 | Agent setup | Yes | README §24 | n/a | |
| 73 | Security documentation | Yes | README §28–29, `PROJECT_EXPLANATION.md` §13, §19 | n/a | |
| 74 | Assumptions | Yes | README §31 | n/a | |
| 75 | Limitations | Yes | README §30, §32 | n/a | |
| 76 | Migrations | Yes | `backend/alembic/versions/0001_initial_schema.py` | Yes — upgrade/downgrade + drift test; verified on PostgreSQL | |
| 77 | .env.example | Yes | `backend/.env.example`, `frontend/.env.example`, `.env.example` (Docker) | Verified tracked, real `.env` ignored | |
| 78 | Tests | Yes | `backend/tests/` (173 tests) | Pass on PostgreSQL (`email_agent_test`) | PostgreSQL is the only database used |
| 79 | Swagger | Yes | `/docs` | Yes | Bearer "Authorize" supported |
| 80 | Demo workflow | Yes | README §35, dashboard checklist | Yes — `test_e2e_flow.py`; live run passed 18/18 checks | |

## Bonus requirements

| Bonus | Status | Location / notes |
|---|---|---|
| Docker | Implemented (not run locally) | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`. Compose YAML validated and the standalone Next.js build verified, but Docker isn't installed on the development machine, so the images were never built or run |
| Email history | Implemented | `/api/v1/emails/history` (+ detail), history UI, tested |
| Retry | Implemented | Retries transient SMTP errors with backoff, `max_send_retries` preference, tested |
| Templates | Not implemented | Listed under future improvements |
| Multiple email accounts | Not implemented | One SMTP account per company (documented assumption) |
| OAuth | Not implemented | Recommended in README §29 (XOAUTH2) |
| Secret encryption | Implemented | Fernet encryption of SMTP passwords at rest (`core/encryption.py`); KMS recommended for production |
| Unit tests | Implemented | Security, encryption, sanitizer, signature helpers, providers, SMTP error classification, config |
| Integration tests | Implemented | API tests through FastAPI + DB for every endpoint, `test_e2e_flow.py`, migration test, PostgreSQL mode |

## Final system test (performed)

* Backend running (`uvicorn main:app --reload`, PostgreSQL `email_agent` at Alembic head `0001_initial_schema`); `/`, `/docs`, `/redoc`, `/openapi.json` → 200.
* Alembic `upgrade head` → `downgrade base` → `upgrade head` verified on a scratch PostgreSQL database (`email_agent_test`).
* Backend tests: 173 passed against PostgreSQL (`email_agent_test`); `email_agent` verified untouched by the test run.
* Frontend: `npm run lint`, `tsc --noEmit`, `npm run build` all clean; dev server running and every page exercised in a browser.
* Live workflow against the running API with real PostgreSQL and a local SMTP server (aiosmtpd): register → login →
  company → SMTP config → SMTP test (real delivery) → signature → preferences → AI draft (mock provider, no key) → edit →
  send (real delivery; From = company account; edited text; signature once; BCC hidden) → history → second company
  isolated (profile, SMTP, signature, history, history-by-ID, sending, AI context): **18/18 checks passed**.
* SMTP passwords confirmed stored as Fernet ciphertext in PostgreSQL. Test accounts were removed afterwards.

## Mandatory requirements missing

None. Two items were not verified against live external services, and are covered by mocked tests instead:
the real Gemini API (no API key was provided) and delivery through a public SMTP provider (tested against a local SMTP server).
