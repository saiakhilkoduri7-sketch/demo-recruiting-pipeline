# TalentMatch AI Recruiting Pipeline

TalentMatch AI is a recruiter-focused candidate matching starter that ingests resumes, removes duplicates, ranks candidates against a job, and exposes a simple dashboard UI.

## Features

- Resume text extraction from .txt, .md, .csv, .pdf, and .docx files
- Candidate deduplication using email, phone, and resume fingerprint
- Skill-based ranking against a job description
- FastAPI backend with health and job endpoints
- Simple recruiter dashboard UI
- SQLite persistence with optional PostgreSQL support
- Docker deployment starter

## Project structure

- `app/services.py` - core matching and deduplication logic
- `app/demo_pipeline.py` - resume ingestion and ranking workflow
- `app/database.py` - SQLite/PostgreSQL persistence layer
- `app/api.py` - FastAPI endpoints and UI serving
- `frontend/index.html` - recruiter dashboard UI
- `tests/` - unit tests for matching and persistence

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.api:app --reload
```

Then open:

- http://localhost:8000/ui
- http://localhost:8000/health

## Run with PostgreSQL

The recommended local setup uses PostgreSQL through Docker Compose:

```bash
docker compose up --build
```

The API container connects to PostgreSQL using:

```text
postgresql://recruiting:recruiting_local_password@db:5432/recruiting_db
```

PostgreSQL data is persisted in the `recruiting_postgres_data` Docker volume. Stop the
services with `docker compose down`; keep the volume to preserve candidates and rankings.
Use a strong password and a managed secret for production deployments.

## Run tests

```bash
python -m pytest -q
```

## Continuous integration and deployment

GitHub Actions runs tests against PostgreSQL, collects coverage, checks formatting with Ruff,
runs a Bandit security scan, and builds the Docker image. The workflow is defined in
`.github/workflows/ci.yml`.

To enable the optional Render deployment workflow, add a repository secret named
`RENDER_DEPLOY_HOOK` containing the deploy hook URL from the Render service. Deployments can
then be triggered automatically from `main` or manually from the Actions tab.

The Render blueprint provisions a free web service, generates a session-signing secret, and
prompts for an admin password and `DATABASE_URL`. Set a unique password with at least 16
characters. For the database, create a project on [Supabase](https://supabase.com/) and open
its **Connect** dialog. Select **Session pooler** and copy its connection string; this works
from Render's IPv4-only free web service and supports this app's persistent PostgreSQL driver.
Replace `[YOUR-PASSWORD]` with your database password, percent-encoding reserved characters.
Ensure the connection string includes `sslmode=require` (append it as a query parameter if
needed), then add it to Render as `DATABASE_URL`. Never commit or share these credentials.
Render prompts for `ADMIN_PASSWORD` and `DATABASE_URL` during initial Blueprint creation; for
an existing service, set them in **Render Dashboard → service → Environment**.

The recruiter dashboard uses an HTTP-only, secure, same-site session cookie. Sign in with
`ADMIN_USERNAME` and `ADMIN_PASSWORD`; the session expires after eight hours. Database routes,
resume uploads, and matching operations require authentication. Production requires TLS on the
database connection, explicit CORS origins and trusted hosts, and the app health check verifies
database connectivity. Server-folder imports are disabled in production; upload candidate files
through the UI instead.

Review [Supabase's current plan limits](https://supabase.com/pricing) and database backup
options before use. Render's free web service can spin down, and its local filesystem is
ephemeral. Free-tier hosting has no production availability guarantee; arrange backups, access
controls, a retention policy, and a privacy/legal review before storing real candidate data.
Matching scores are assistive signals only and must not be used as the sole basis for hiring
decisions. Outlook mailbox variables are only needed when mailbox ingestion is enabled.

## Production notes

- Use environment variables for config and secrets
- Set `DATABASE_URL` for PostgreSQL in production
- Set `OUTLOOK_SHARED_MAILBOX` and `GRAPH_ACCESS_TOKEN`, then call `POST /mailbox/ingest` to import unread resumes from Outlook
- Configure Google OAuth to connect Gmail from the dashboard and manually import unread resume attachments
- Agent 2 can call `POST /jobs/{job_id}/match-database` to rank candidates stored by Agent 1
- Deploy behind Gunicorn + Uvicorn or Docker
- Use a managed database and monitoring for real workloads

### Outlook handoff

Agent 1 calls `POST /mailbox/ingest`. The service reads unread
messages through Microsoft Graph, extracts text from TXT, PDF, and DOCX attachments, and upserts
each candidate into the configured database using the message ID as the stable candidate ID.

```json
{
	"top": 25
}
```

The mailbox address can be supplied in the request or configured with `OUTLOOK_SHARED_MAILBOX`.
Keep the Graph token in the `GRAPH_ACCESS_TOKEN` environment variable. In Azure Entra ID, grant
the application Microsoft Graph `Mail.Read` application permission and grant admin consent for
the tenant. Agent 2 then calls:

```text
POST /jobs/{job_id}/match-database
```

That endpoint reads candidates from the database, removes duplicates, ranks them against the job,
and stores the ranking results.

### Gmail demo connector

The recruiter dashboard can connect one Google account using OAuth and Google's read-only Gmail
scope. In Google Cloud Console, create a project, enable the Gmail API, configure the OAuth consent
screen as **External**, add your own Gmail address as a test user, and create a **Web application**
OAuth client. Register this exact authorized redirect URI:

```text
https://talentmatch-ai-hy1n.onrender.com/auth/google/callback
```

In Render service Environment, set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and
`GOOGLE_REDIRECT_URI` to the OAuth client values and redirect above. Keep the client secret private.
After Render redeploys, sign in to TalentMatch and use **Connect Gmail**, then **Import unread mail**.
The app requests Gmail read-only access, checks only unread messages in the inbox, accepts PDF,
DOCX, TXT, MD, and CSV attachments, leaves messages unread, and stores usable candidate profiles
in the existing `DATABASE_URL` database. Messages without a supported readable resume are skipped.
This is a manual import, not an inbox watcher. OAuth credentials are held in application memory for
this demo deployment; reconnect after a service restart or redeploy. Keep the service to one worker
for this in-memory demo connector. Google OAuth apps left in Testing mode may require the Gmail
address to be listed as a test user and can have refresh tokens expire after seven days.
