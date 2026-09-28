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

## Production notes

- Use environment variables for config and secrets
- Set `DATABASE_URL` for PostgreSQL in production
- Set `OUTLOOK_SHARED_MAILBOX` and `GRAPH_ACCESS_TOKEN`, then call `POST /mailbox/ingest` to import unread resumes from Outlook
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
