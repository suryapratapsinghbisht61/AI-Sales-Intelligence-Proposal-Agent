# SalesPilot AI

AI sales intelligence and proposal platform for B2B teams: a cited knowledge base, evidence-tracked prospect research,
grounded proposal drafting, and server-enforced approvals.

```
frontend/  Next.js 16 (App Router) + Tailwind + shadcn/ui. Proxies /api/v1 to the backend (same-origin cookie auth).
backend/   FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL/pgvector + LangChain/LangGraph.
           app/api        HTTP routes (thin)        app/workflows  LangGraph: qa, research, proposal
           app/services   retrieval, ingestion, LLM access/usage, jobs, storage, scoring, web fetch
           app/worker.py  background worker (Postgres-backed job queue, no Redis needed)
```

## Run locally

Prereqs: Docker, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 20+, and a model provider (Ollama works offline).

```sh
cp .env.example .env                      # then set CHAT_MODEL / EMBEDDING_MODEL (see below)
docker compose up -d db                   # Postgres 17 + pgvector on :5432
cd backend && uv sync && uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000   # API  (terminal 1)
uv run python -m app.worker               # jobs (terminal 2)
cd ../frontend && npm install && npm run dev   # UI on http://localhost:3000 (terminal 3)
```

Free local models: `ollama pull llama3.2 nomic-embed-text`, then `CHAT_MODEL=ollama:llama3.2`,
`EMBEDDING_MODEL=ollama:nomic-embed-text`. Small local models answer cited questions well but extract few research
facts; for production quality use e.g. `CHAT_MODEL=anthropic:claude-sonnet-5-5`, `FAST_MODEL=anthropic:claude-haiku-5-5`,
`EMBEDDING_MODEL=openai:text-embedding-3-small` with `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`.
The database stores 768-dim vectors (`EMBEDDING_DIM`); OpenAI embeddings are shortened to match, other providers must
natively produce 768 dims. Changing the dimension needs a new migration and re-ingesting documents.

Without a model configured, the app still runs: uploads fail with an explanatory error (retryable later), knowledge
search falls back to keyword search, and chat returns a 503 explaining what to configure.

Tests: `cd backend && uv run pytest` (needs the compose `db`; creates/drops `salespilot_test`).
API docs: http://localhost:8000/api/docs

## Environment variables

See `.env.example`. Key ones: `DATABASE_URL`, `FRONTEND_ORIGIN` (CORS + CSRF origin check), `COOKIE_SECURE=true` in
production, `CHAT_MODEL`, `FAST_MODEL`, `EMBEDDING_MODEL`, `MODEL_PRICES` (optional cost estimates),
`ORG_MONTHLY_TOKEN_BUDGET`, `STORAGE_BACKEND=s3` + `S3_BUCKET` (+ `S3_ENDPOINT_URL` for MinIO/R2) and AWS credentials,
`MAX_UPLOAD_MB`, `RATE_LIMIT_PER_MINUTE`. Frontend: `BACKEND_URL` (default `http://localhost:8000`).

## How the safeguards work

- **Tenancy**: every tenant row has `org_id`; routes load rows via `get_owned()` (404 for other orgs); retrieval filters
  `org_id` and current document version in SQL before anything reaches a model. Cross-tenant tests in `backend/tests`.
- **Roles** (`owner`, `admin`, `sales_manager`, `sales_rep`): `PERMISSIONS` in `app/security.py`, checked server-side.
- **Auth**: argon2 password hashes, random session tokens stored hashed, httpOnly SameSite=Lax cookie, Origin check on
  writes, password reset tokens (1h, single use, signs out all sessions).
- **Citations**: the model may only cite ids of retrieved chunks; anything else is dropped. No evidence -> no model call.
- **Research**: facts are `verified` only if their quote appears verbatim in the fetched page; criteria without a
  verified quote become `unknown`. Scores are computed in code from a versioned rubric. Web fetching honours robots.txt,
  stays on the prospect's domain and refuses private IPs.
- **Proposals**: pricing is computed in Decimal from the approved price list (the model never writes prices); money
  amounts, guarantee-style claims and placeholders are flagged on every version, including manual edits.
- **Approvals**: one pending request per proposal; approvers need `approvals.decide`, cannot approve their own request
  (except owners), and approval fails if the proposal changed after submission.

## Deploying

- **Backend**: build `backend/Dockerfile`; run the same image twice: API (`uvicorn ...`) and worker
  (`python -m app.worker`). Any container host with persistent runtime (ECS/Fargate, Fly, Render, Railway).
- **Database**: managed Postgres with the `vector` extension (RDS, Neon, Supabase). Run `alembic upgrade head` as a
  release step, reviewed, never automatically against production. Enable automated backups / PITR.
- **Files**: `STORAGE_BACKEND=s3` with a private bucket; the API streams downloads after an org check, nothing is public.
- **Frontend**: Vercel (root `frontend/`), set `BACKEND_URL` to the API's URL. Set `FRONTEND_ORIGIN` on the API to
  the site's URL and `COOKIE_SECURE=true`.

Recovery: failed jobs keep their error on the document / research run / proposal and can be retried from the UI. Jobs
left `running` by a crashed worker are reclaimed after 15 minutes. Ingestion is idempotent per document version.

## Status

Implemented and tested: everything above, plus CSV import/export with duplicate detection, outreach drafts (never
auto-sent), proposal versions/regeneration/DOCX export, analytics, usage and audit log.

Not implemented (shown honestly as "Coming soon" in the UI): Google Drive, SharePoint, HubSpot, Salesforce, Gmail,
Calendar and Slack integrations; transactional email (reset/invite links are logged/displayed instead); PDF export;
OCR for scanned PDFs; billing; Postgres row-level security; a shared rate limiter for multiple API replicas.
