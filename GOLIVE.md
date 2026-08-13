# GOLIVE — your action items

Everything in the repo runs **locally with no accounts** (`USE_MOCKS=true`). This
file is the single ordered checklist of the things **only you can do** — create
free accounts, paste keys, click deploy. Each step says exactly which value goes
into which `DATACHAT_*` env var. Nothing here costs money: every tier is a
permanent free tier.

> Env var convention: the app reads settings with the `DATACHAT_` prefix
> (e.g. `DATACHAT_GEMINI_API_KEY`). `.env.example` documents every variable.

**Where things run (multi-service topology):**

| Service | Host | Notes |
|---|---|---|
| Frontend | Vercel (free) | thin streaming UI |
| Backend (BFF + agent) | Render (free) | the request path |
| **AI (Ollama)** | **your PC's GPU** | a separate, **secured** service via a token-gated tunnel |
| Postgres + pgvector | Neon (free) | app + analytics schemas |
| Redis | Upstash (free) | cache, rate-limit, breaker state |
| MLflow | HF Space (free) | traces + prompt registry |
| Ingestion / Eval | GitHub Actions / CLI | offline jobs, not always-on |

The AI being its own network-boundary service (Ollama) *is* the microservice
extraction of the LLM gateway — swappable and independently secured, without
splitting the synchronous request path.

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

## 1. AI — your Ollama on your PC (primary), fronted by a secured tunnel

The AI runs on **your machine's GPU** (a separate "AI service" the online backend
calls over the network). The online backend reaches it through a **Cloudflare
tunnel protected by a bearer token**, so no one who finds the URL can abuse your
GPU. Optionally add Gemini/Groq as an automatic fallback (see step 1c).

**1a. Run Ollama locally**
```bash
# install from https://ollama.com, then:
ollama pull llama3.2          # small, fits an 8 GB 2060; or qwen2.5:3b / phi3.5
ollama serve                  # serves the OpenAI-compatible API on :11434
```

**1b. Expose it securely with a Cloudflare tunnel + a token**
The endpoint must require a secret so only your backend can use it. Easiest path:
put a tiny auth proxy in front of Ollama and tunnel that.
```bash
# terminal 1 — auth proxy that requires  Authorization: Bearer <YOUR_SECRET>
#   (use Caddy, or `cloudflared` + Cloudflare Access service token, or nginx).
# Example with Caddy (Caddyfile):
#   :11435 {
#     @noauth not header Authorization "Bearer YOUR_LONG_RANDOM_SECRET"
#     respond @noauth 401
#     reverse_proxy localhost:11434
#   }
caddy run

# terminal 2 — tunnel the proxy port to a public HTTPS URL
cloudflared tunnel --url http://localhost:11435
# note the https://<random>.trycloudflare.com URL (or map a named tunnel to a domain)
```
Then set on the **online backend** (step 5):
```
DATACHAT_USE_MOCKS=false
DATACHAT_OLLAMA_ENABLED=true
DATACHAT_OLLAMA_BASE_URL=https://<your-tunnel-host>/v1
DATACHAT_OLLAMA_API_KEY=YOUR_LONG_RANDOM_SECRET   # must match the proxy
DATACHAT_OLLAMA_MODEL=llama3.2
DATACHAT_LLM_TIMEOUT_S=90                          # give the GPU headroom
```
The backend's own per-IP rate limit + global daily quota add a second layer, so
even authorized traffic can't hammer your GPU.

**1c. (Optional) cloud fallback — recommended**
If Ollama ever OOMs or reloads a model, the circuit breaker trips and the demo
keeps answering on free cloud tiers:
- **Gemini** — https://aistudio.google.com/app/apikey → `DATACHAT_GEMINI_API_KEY=<key>`
- **Groq** — https://console.groq.com/keys → `DATACHAT_GROQ_API_KEY=<key>`

Leave these unset to run **Ollama-only**. (OpenRouter stays off —
`DATACHAT_OPENROUTER_ENABLED=false` — to remain $0.)

> **Local dev with Ollama (no tunnel):** set `DATACHAT_OLLAMA_ENABLED=true` and
> `DATACHAT_OLLAMA_BASE_URL=http://host.docker.internal:11434/v1` (from a container)
> or `http://localhost:11434/v1` (bare uvicorn), and `DATACHAT_USE_MOCKS=false`.

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

## Final checklist — **DONE 13 Aug 2026**

Live: **https://data-chat-seven.vercel.app/** → **https://datachat-api-wmpd.onrender.com**

- [x] `DATACHAT_USE_MOCKS=false`, with **Groq** as the provider
- [x] `alembic upgrade head` against Neon (roles + pgvector created) — runs automatically from `backend/start.sh` on every deploy
- [x] seed ingested (idempotent, checksum-gated, also from `start.sh`)
- [x] backend live on Render, `/ready` returns 200
- [x] frontend live on Vercel, `NEXT_PUBLIC_API_BASE` points at the backend
- [x] CORS set to the Vercel origin
- [x] keep-warm pinging `/ready` (repo variable `KEEP_WARM_URL`, every 12 min)
- [x] `.env` is **not** committed (only `.env.example` is tracked)
- [ ] Ollama tunnel — **deliberately not part of the deployed path**, see below
- [ ] `docs/hero.gif` — see [docs/README.md](docs/README.md)
- [ ] the two "YOUR WORDS" README sections, in your voice

### Why Ollama is not the deployed provider

A public URL has to answer when your PC is off, and `cloudflared tunnel --url`
issues a **new random hostname on every restart** — so every reboot would mean
editing the Render env and redeploying. Groq's free tier is the always-on
provider; Ollama stays one env flag away for a live demo.

### Four gotchas this deploy actually hit

Recorded because each cost real time and none of them says what it means:

| Symptom | Cause | Fix |
|---|---|---|
| Blueprint: `render.yaml not found` | The file had never been pushed | `git push` |
| `Exited with status 127` | Render shells `dockerCommand` already, so an inline `sh -c "a && b"` looked for one command named `a && b` | Moved to `backend/start.sh` |
| `error parsing value for field "cors_origins"` | pydantic-settings JSON-decodes list fields, so a plain URL is a JSON syntax error | Config now takes plain / comma-separated / JSON |
| UI loads, every request blocked | `CORS_ORIGINS` had a **trailing slash**; a browser `Origin` never has a path | Now stripped automatically |

The last three are fixed in code, so a fresh deploy of this repo will not hit them.

### Turning on your own GPU later

1. `deploy\start-ai.bat` — starts Caddy (auth proxy) + the Cloudflare tunnel
2. Verify the lock before exposing it: `curl -H "Authorization: Bearer <token>" https://<host>/v1/models` must return models, and the same call **without** the header must return `401`
3. On Render set: `DATACHAT_OLLAMA_ENABLED=true`, `DATACHAT_OLLAMA_BASE_URL=https://<host>/v1` (note the `/v1`), `DATACHAT_OLLAMA_API_KEY=<same token as Caddy>`, `DATACHAT_OLLAMA_MODEL=qwen2.5:7b-instruct`
4. Ollama then leads for every task — `TaskAwarePolicy` puts a present Ollama ahead of cloud providers
5. After the demo set `DATACHAT_OLLAMA_ENABLED=false`, so requests don't pay a timeout before falling back
