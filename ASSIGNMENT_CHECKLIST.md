# Assignment Compliance Checklist

"Tested" means covered by automated tests in `backend/tests/` (run `cd backend && pytest`; the suite
runs on a dedicated PostgreSQL test database) and, where stated, verified manually against the
running application. Paths are relative to the repository root; backend paths are under
`backend/app/` unless shown otherwise.

Only features that exist in the code are marked as implemented. Items that were **not** verified
against a live external service are stated explicitly.

## Core requirements

| # | Requirement | Implemented | Location | Tested | Notes |
|---|---|---|---|---|---|
| 1 | Company name | Yes | `models/company.py`, `schemas/company.py` | Yes — `test_company.py` | Required, 1–200 chars |
| 2 | Company description / overview | Yes | same | Yes | Required |
| 3 | Website | Yes | same, `schemas/common.py` | Yes | http(s) only; bare domains normalized |
| 4 | Industry | Yes | same | Yes | |
| 5 | Company location | Yes | same | Yes | |
| 6 | Services / products | Yes | `company_services` table | Yes | Ordered child table |
| 7 | Target customers | Yes | `target_customers` table | Yes | |
| 8 | Value propositions | Yes | `value_propositions` table | Yes | |
| 9 | Contact person, email, phone, address | Yes | columns on `companies` | Yes | Email and phone validated |
| 10 | Social media / other links | Yes | `social_links` table | Yes | URL validated; unique per company |
| 11 | Create / view / edit / update profile | Yes | `api/v1/endpoints/company.py` (POST / GET / PUT) | Yes | Frontend page `company` |
| 12 | Email address | Yes | `models/email.py` `EmailAccount` | Yes — `test_email_accounts.py`, `test_email_config.py` | |
| 13 | SMTP host / port | Yes | same | Yes | Host validated; provider presets for Gmail / Outlook |
| 14 | Username | Yes | same | Yes | Defaults to the email address |
| 15 | Password / App Password | Yes | `encrypted_smtp_password` | Yes | Write-only, Fernet-encrypted; Gmail App Password spaces removed |
| 16 | Encryption / security type | Yes | `SecurityType` (NONE / STARTTLS / SSL_TLS) | Yes — `test_smtp.py` (all three modes) | |
| 17 | Sender name | Yes | `EmailAccount.sender_name` (+ preference override) | Yes | Reply-to also supported |
| 18 | Test email configuration | Yes | `POST /email-accounts/{id}/test`, legacy `POST /email-config/test` | Yes — `test_smtp.py`, `test_gmail_oauth.py`, `test_test_email_history.py` | Records a history row with `is_test: true`. Verified live with Mailpit / a local SMTP server and with Gmail OAuth. **Real Gmail SMTP not demonstrated** (no working App Password) |
| 19 | Password not exposed in API responses | Yes | separate request / response schemas | Yes — `test_security.py`, `test_email_accounts.py` | Only `password_configured` / `oauth_connected` |
| 20 | Password not exposed in logs | Yes | no credential logging + `core/logging.py` redaction | Yes — full-flow log capture tests | Verified in real backend / worker logs during the Gmail OAuth run |
| 21 | Password not in frontend source | Yes | frontend only uses `NEXT_PUBLIC_API_URL` | Verified | |
| 22 | Password not in database queries | Yes | encrypted column; `hide_parameters=True` | Yes | Ciphertext only at rest |
| 23 | Production credential storage explained | Yes | README §29 | n/a | Secrets manager, KMS envelope encryption, OAuth |
| 24 | Email signature (reusable) | Yes | `/api/v1/signature` | Yes — `test_signature.py` | |
| 25 | Signature available to the agent | Yes | `services/agent/context.py` | Yes — `test_agent_signature.py` | Policy: appended on send / in body / none |
| 26 | Preference: sender name | Yes | `/api/v1/preferences` | Yes — `test_preferences.py` | |
| 27 | Preference: reply-to | Yes | same | Yes — `Reply-To` header asserted | |
| 28 | Preference: default signature / auto-append | Yes | signature settings, summary in preferences | Yes | |
| 29 | Preference: HTML / plain text | Yes | `default_format`, per-send override | Yes | HTML has a plain-text alternative |
| 30 | Preference: sending limits | Yes | `daily_send_limit`, `max_recipients_per_email`, `max_send_retries` | Yes — 429 / 400 / retry tests | Test emails don't count toward the daily limit |
| 31 | Preference: CC / BCC defaults | Yes | `default_cc`, `default_bcc` | Yes | SMTP BCC only in the envelope |
| 32 | Extensible preferences design | Yes | `extra_settings` JSON column | Yes | No migration needed for new settings |
| 33 | Agent uses company overview | Yes | `services/agent/context.py` | Yes — `test_agent.py` | |
| 34 | Agent uses products / services | Yes | same | Yes | |
| 35 | Agent uses target customers | Yes | same | Yes | |
| 36 | Agent uses value propositions | Yes | same | Yes | |
| 37 | Agent uses contact information | Yes | same | Yes | |
| 38 | Agent uses email signature | Yes | same | Yes | |
| 39 | Agent uses sender identity | Yes | same (selected or default account + preference overrides) | Yes | |
| 40 | Free-tier LLM, named and configurable | Yes | `services/llm/gemini.py` (Google Gemini) | Yes — simulated responses (`test_llm_providers.py`) | Live generation verified once (2026-09-29, `fallback_used: false`); earlier requests returned HTTP 503 `UNAVAILABLE` (Google high demand) |
| 41 | Mock / fallback implementation | Yes | `services/llm/mock.py`, fallback in `services/agent/email_agent.py` | Yes — no key, provider failure, fallback disabled → 503 | Verified live when Gemini returned 503 |
| 42 | Send using the user's configured account | Yes | `services/email_sender.py`, `services/email_delivery.py` | Yes — `test_email_sending.py`, `test_background_delivery.py`, e2e | Verified live via Gmail OAuth / Gmail API and via Mailpit |
| 43 | No hard-coded system sender | Yes | From = selected or default company account | Yes — two companies send through their own accounts | No global SMTP settings exist |
| 44 | Python, FastAPI | Yes | `backend/app` | Yes | |
| 45 | PostgreSQL | Yes | psycopg 3 | Yes — the whole suite runs on PostgreSQL | |
| 46 | Pydantic models | Yes | `schemas/`, settings | Yes | |
| 47 | SQLAlchemy ORM | Yes | SQLAlchemy 2.1 typed models | Yes | |
| 48 | Proper error handling | Yes | `core/exceptions.py`, `core/error_handlers.py` | Yes — `test_error_handling.py` | One JSON error shape |
| 49 | Environment variables for secrets | Yes | `core/config.py` | Yes — `test_config.py` | `.env` git-ignored |
| 50 | Database: profile + child tables | Yes | `models/company.py`, migrations | Yes — `test_models.py`, `test_migrations.py` | |
| 51 | Database: email configuration, signature, preferences | Yes | `email_accounts`, `email_signatures`, `email_preferences` | Yes | |
| 52 | Multiple users / companies | Yes | `users`, `companies` (1:1), all data company-scoped | Yes | |
| 53 | Authentication | Yes | register / login / me | Yes — `test_auth.py` | JWT (listed as an advantage) |
| 54 | Company data isolation | Yes | `get_current_company`, company-filtered lookups | Yes — `test_isolation.py` + per-feature tests | Selected email account ownership checked server-side |
| 55 | Next.js frontend | Yes | `frontend/` (Next.js 16, TypeScript) | Lint, type check, production build; manual browser testing | No automated UI tests |
| 56 | Input validation | Yes | Pydantic schemas + client-side checks | Yes | |
| 57 | SQL injection prevention | Yes | ORM with bound parameters | Yes — `test_security.py` | |
| 58 | Secure API design | Yes | auth, isolation, rate limits, headers, CORS, SSRF guard | Yes — `test_hardening.py`, `test_cors.py` | |
| 59 | No credentials in Git | Yes | `.gitignore`, placeholder-only `.env.example` files | Verified by scan | |
| 60 | README (overview, architecture, stack, install, env vars, DB setup, API docs, email setup, agent, security, assumptions, limitations) | Yes | `README.md` | n/a | |
| 61 | `.env.example` (`DATABASE_URL`, `SECRET_KEY`, `LLM_API_KEY`, …) | Yes | `backend/.env.example`, `.env.example` (Docker), `frontend/.env.example` | Verified placeholders only | |
| 62 | Database schema / migrations | Yes | `backend/alembic/versions/0001`–`0006` | Yes — upgrade, downgrade, drift, data migration | |
| 63 | API documentation | Yes | Swagger `/docs`, ReDoc `/redoc`, README §22 | Yes — `test_api_docs.py` | |

## Bonus items

| Bonus | Implemented | Tested | Notes |
|---|---|---|---|
| JWT authentication | Yes | Yes | HS256, pinned algorithm, expiry, forged / `alg: none` tokens rejected |
| Docker / Docker Compose | Yes | Run for real | db, redis, backend, worker, frontend (+ Mailpit profile) built and healthy |
| Background email processing (Celery + Redis) | Yes | Yes (eager) + real runs | Real end-to-end runs: Mailpit (Docker) and Gmail API (local worker + Docker Redis) |
| Email sending history / logs | Yes | Yes | Delivery status, attempts, account used, task id, test-email records |
| Retry mechanism | Yes | Yes + real run | Bounded by `max_send_retries`; exponential backoff with jitter in background mode; real retry verified with a paused Mailpit |
| Email templates | Yes | Yes | Safe `{{ variable }}` rendering, preview, agent integration |
| Multiple email accounts per company | Yes | Yes | Default account (partial unique index), explicit selection (API + *Send from* picker on the agent page), server-side ownership checks |
| OAuth-based Gmail integration | Yes | Yes (fake Google) + real run | Real Google connection, Test email and background send verified |
| OAuth-based Outlook integration | **No** | — | Not implemented; Outlook is supported through SMTP only |
| Secret / encryption management | Yes | Yes | Fernet for SMTP passwords, OAuth tokens, PKCE verifiers; production refuses a missing key |
| Unit and integration tests | Yes | — | pytest on PostgreSQL; fakes for SMTP, Google and the LLM |
| Swagger / OpenAPI | Yes | Yes | `/docs` with bearer *Authorize* |

## Real-world verification

| Item | Result |
|---|---|
| Gmail OAuth connection (real Google Cloud client, Testing mode) | Verified |
| Gmail API delivery (Test email, and API → Redis → Celery → Gmail API) | Verified — `SENT` on attempt 1, token refreshed automatically, no secrets in logs or API responses |
| Local SMTP delivery (Mailpit / local server) | Verified |
| Docker Compose stack + Celery delivery + retry via Mailpit | Verified |
| Real Gmail SMTP delivery | **Not demonstrated** (a working Gmail App Password was not available) |
| Live Gemini generation | Verified once (2026-09-29: `provider: gemini`, `fallback_used: false`); earlier attempts returned HTTP 503 `UNAVAILABLE` and the mock fallback was verified |
| Gmail OAuth inside the Docker stack | Not configured / not tested |

## Mandatory requirements missing

None. One item was verified only with automated tests (not against the live service): real Gmail
SMTP delivery — see above.
