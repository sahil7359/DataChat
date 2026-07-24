# GOLIVE — your action items

Everything in the repo runs **locally with no accounts** (`USE_MOCKS=true`). This
file is the single ordered checklist of the things **only you can do** — create
free accounts, paste keys, click deploy. Each step says exactly which value goes
into which `DATACHAT_*` env var. Nothing here costs money: every tier is a
permanent free tier.

> Env var convention: the app reads settings with the `DATACHAT_` prefix
> (e.g. `DATACHAT_GEMINI_API_KEY`). `.env.example` documents every variable.

---

## 0. Run it locally first (no accounts, ~5 min)

```bash
git clone <your-fork-url> datachat && cd datachat
cp .env.example .env          # defaults: USE_MOCKS=true
docker compose up --build     # postgres+pgvector, redis, backend, frontend, mlflow
docker compose exec backend python -m ingestion.run --dataset seed
```

- App → http://localhost:3000 · API docs → http://localhost:8000/docs ·
  Dashboard → http://localhost:3000/dashboard · MLflow → http://localhost:5000

You now have a working demo on mocks. The rest wires real services.

---

## 1. LLM keys (free)

1. **Gemini** — https://aistudio.google.com/app/apikey → *Create API key*.
   → `DATACHAT_GEMINI_API_KEY=<key>`
2. **Groq** — https://console.groq.com/keys → *Create API Key*.
   → `DATACHAT_GROQ_API_KEY=<key>`
3. Flip to real models: `DATACHAT_USE_MOCKS=false`.
   (OpenRouter stays off — `DATACHAT_OPENROUTER_ENABLED=false` — to remain $0.)

## 2. Database — Neon (free, Postgres 16 + pgvector)

1. https://neon.tech → sign up → *Create project* (Postgres 16).
2. Copy the connection string. Convert it to the async driver form:
   `postgresql+asyncpg://USER:PASSWORD@HOST/DB?sslmode=require`
   → `DATACHAT_DATABASE_URL=<that>`
3. Choose a strong password for the read-only executor role:
   → `DATACHAT_EXECUTOR_ROLE_PASSWORD=<pick-one>`
   and set the executor URL (same host/db, user `datachat_exec`):
   → `DATACHAT_EXECUTOR_DATABASE_URL=postgresql+asyncpg://datachat_exec:<that-pw>@HOST/DB?sslmode=require`
4. Apply the schema, roles, and seed data:
   ```bash
   cd backend
   uv run alembic upgrade head          # creates schemas, pgvector, and the RO roles
   uv run python -m ingestion.run --dataset seed   # or: --dataset wdi / owid (network)
   ```

## 3. Cache — Upstash Redis (free)

1. https://upstash.com → *Create Database* (Redis, single region).
2. Copy the `rediss://` URL → `DATACHAT_REDIS_URL=<url>`.

## 4. MLflow (optional, free)

- Local/dev: the docker-compose `mlflow` service already works.
- Hosted: create a **Hugging Face Space** (Docker, MLflow) with the Neon DB as the
  backend store, then → `DATACHAT_MLFLOW_TRACKING_URI=<space-url>`.
- If you skip this, tracing degrades to a no-op — the app still runs.

## 5. Deploy the backend — Render (free web service)

1. https://render.com → *New* → *Web Service* → connect your GitHub repo.
2. Root directory `backend`, environment **Docker** (uses `backend/Dockerfile`).
3. Add env vars from your `.env` (all the `DATACHAT_*` above). **Do not** commit `.env`.
4. Deploy. Note the URL, e.g. `https://datachat-api.onrender.com`.
5. Health check path: `/ready`.

## 6. Deploy the frontend — Vercel (free, Hobby)

1. https://vercel.com → *Add New Project* → import the repo, root `frontend`.
2. Set env var `NEXT_PUBLIC_API_BASE=https://<your-render-url>/api/v1`.
3. Deploy. Vercel gives you the public URL.
4. Add that URL to the backend's `DATACHAT_CORS_ORIGINS` and redeploy the backend.

## 7. Keep-warm (free, avoids cold starts)

- Option A: in the GitHub repo, set a **repository variable** `KEEP_WARM_URL` to
  `https://<your-render-url>/ready`. The `keep-warm` workflow pings it every 12 min.
- Option B: https://cron-job.org → new cron-job hitting the same URL every ~12 min.

## 8. Turn on CI (already written)

- Push to GitHub — `.github/workflows/ci.yml` runs lint, type, tests (with a live
  Postgres+Redis), the security scanners, and the eval gate on every PR. No secrets
  are needed for CI (it uses service containers + mocks).

---

## Final checklist

- [ ] `USE_MOCKS=false` and both LLM keys set
- [ ] `alembic upgrade head` run against Neon (roles + pgvector created)
- [ ] seed (or wdi/owid) ingested
- [ ] backend live on Render, `/ready` returns 200
- [ ] frontend live on Vercel, `NEXT_PUBLIC_API_BASE` points at the backend
- [ ] CORS updated with the Vercel URL
- [ ] keep-warm pinging `/ready`
- [ ] `.env` is **not** committed (only `.env.example` is tracked)

Drop the live URL and a short demo clip into `README.md` where the placeholders
are, and you're done.
