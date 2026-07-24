# Deploy DataChat — beginner walkthrough

Follow this top to bottom. Every step says exactly what to click and paste, with a
**✅ Check** so you know it worked before moving on. Budget ~1 hour the first time.
Everything is free (an optional domain is the only thing that could cost money).

**What you'll end up with:** a public link (on Vercel) you can open from your phone
or send to a recruiter. It talks to a backend on Render, which uses a free cloud
database + cache, and calls the **AI running on your own PC** through a secure tunnel.

```
Phone/recruiter → Vercel (frontend) → Render (backend) → your PC's Ollama (AI)
                                            ↘ Neon (database)  ↘ Upstash (cache)
```

---

## Part 0 — Try it locally first (10 min, builds confidence)

This proves the app works before you deploy anything.

1. Install **Docker Desktop** and start it.
2. Open a terminal in the project folder and run:
   ```bash
   cp .env.example .env
   docker compose up --build
   ```
3. Wait for the logs to settle (first build takes a few minutes).

**✅ Check:** open http://localhost:3000, type *"Top 10 countries by CO₂ per capita
in 2022"*, and you should see it stream SQL → a table → a chart. (This uses a fake
AI — real AI comes when you add Ollama below.) Press `Ctrl+C` to stop.

---

## Part 1 — Put the code on GitHub

Render and Vercel deploy *from* GitHub, so it needs to live there.

1. Make a free account at github.com.
2. Install **GitHub CLI** (cli.github.com), then in the project folder run:
   ```bash
   gh auth login
   gh repo create datachat --public --source=. --remote=origin --push
   ```
   (No CLI? Create an empty repo on github.com and follow its "push an existing
   repository" commands.)

**✅ Check:** your code appears at `https://github.com/<you>/datachat`, and the
**Actions** tab shows the CI pipeline running.

---

## Part 2 — Start the AI on your PC

Your GPU is the AI. We run it, lock it behind a password, and give it a public URL.

1. Install **Ollama** (ollama.com) — it runs automatically in your system tray.
2. Install **Caddy** (caddyserver.com/download) and **cloudflared**
   (github.com/cloudflare/cloudflared/releases) — put both `.exe` files somewhere on
   your PATH (e.g. `C:\Windows` or add them to PATH).
3. Make your secret password:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Copy the output. Copy `deploy/Caddyfile.example` to `deploy/Caddyfile` (that copy
   is git-ignored, so your secret never lands in git), replace
   `CHANGE_ME_LONG_RANDOM_SECRET` with your secret, and save. **Keep this secret** —
   you'll paste it into Render too.
4. Double-click **`deploy/start-ai.bat`**. Two windows open (Caddy + the tunnel).

**✅ Check:** the tunnel window prints a line like
`https://something-random.trycloudflare.com`. **Copy that URL** — you'll need it in
Part 5. Keep both windows open.

> Tip: the free tunnel URL changes if you restart it. Since your PC stays on, that's
> rare — if it ever changes, just update the one value in Render (Part 5).

---

## Part 3 — Free database (Neon)

1. Sign up at neon.tech → **Create project** (accept the Postgres 16 defaults).
2. On the project page, copy the **connection string**. It looks like:
   `postgresql://USER:PASSWORD@ep-xxx.neon.tech/neondb?sslmode=require`
3. You'll turn it into two values in Part 5 — just keep it handy for now. Also pick a
   second password for the read-only role (any strong string), keep it too.

**✅ Check:** you have the Neon connection string and your chosen exec-role password
saved in a notepad.

---

## Part 4 — Free cache (Upstash)

1. Sign up at upstash.com → **Create Database** → Redis → pick a region → Create.
2. Copy the **`rediss://…`** connection URL.

**✅ Check:** the `rediss://…` URL is in your notepad.

---

## Part 5 — Deploy the backend (Render)

1. Sign up at render.com and connect your GitHub.
2. Click **New → Blueprint**, pick your `datachat` repo. Render reads `render.yaml`
   and proposes the `datachat-api` service. Click **Apply**.
3. Open the service → **Environment** tab → fill the values marked "paste":

   | Key | Value |
   |---|---|
   | `DATACHAT_DATABASE_URL` | your Neon string, but change the start to `postgresql+asyncpg://` and keep `?sslmode=require` |
   | `DATACHAT_EXECUTOR_DATABASE_URL` | same host/db but user `datachat_exec` and *your exec password*: `postgresql+asyncpg://datachat_exec:EXECPW@ep-xxx.neon.tech/neondb?sslmode=require` |
   | `DATACHAT_EXECUTOR_ROLE_PASSWORD` | your exec password (same as above) |
   | `DATACHAT_REDIS_URL` | your Upstash `rediss://…` URL |
   | `DATACHAT_OLLAMA_BASE_URL` | the tunnel URL from Part 2 **with `/v1` added**: `https://something.trycloudflare.com/v1` |
   | `DATACHAT_OLLAMA_API_KEY` | your Caddy secret from Part 2 |
   | `DATACHAT_CORS_ORIGINS` | leave blank for now (Part 7) |

   (Optional: `DATACHAT_GEMINI_API_KEY` / `DATACHAT_GROQ_API_KEY` for fallback — free
   keys from aistudio.google.com and console.groq.com.)
4. **Save** → Render redeploys. It automatically runs the database setup + seed, then
   starts.

**✅ Check:** when the deploy is "Live", open `https://<your-render-name>.onrender.com/ready`
in a browser — you should see `{"status":"ready", ...}`. Note this backend URL.

---

## Part 6 — Deploy the frontend (Vercel)

1. Sign up at vercel.com → **Add New… → Project** → import your `datachat` repo.
2. Set **Root Directory** to `frontend` (click Edit next to it).
3. Under **Environment Variables**, add:
   `NEXT_PUBLIC_API_BASE` = `https://<your-render-name>.onrender.com/api/v1`
4. Click **Deploy**.

**✅ Check:** Vercel gives you a URL like `https://datachat-you.vercel.app`.
**This is your public link.**

---

## Part 7 — Connect them + keep it awake

1. Back in **Render → Environment**, set:
   `DATACHAT_CORS_ORIGINS` = `["https://datachat-you.vercel.app"]`
   (use your real Vercel URL). Save → it redeploys.
2. In **GitHub → your repo → Settings → Secrets and variables → Actions →
   Variables**, add a variable `KEEP_WARM_URL` =
   `https://<your-render-name>.onrender.com/ready`. This pings your backend every 12
   minutes so it doesn't fall asleep.

---

## Final check — from your phone

1. Make sure the two windows from Part 2 are still running on your PC.
2. Open your Vercel link **on your phone** (mobile data, not your home wifi — proves
   it's truly online).
3. Ask *"Top 10 countries by CO₂ per capita in 2022"*.

**✅ Check:** you see streamed SQL → a table → a chart — generated by the GPU in your
room. Visit `…vercel.app/dashboard` to watch live metrics.

🎉 Done. Send that Vercel link to anyone.

---

## When you restart your PC

Just double-click `deploy/start-ai.bat` again. If the tunnel prints a **new** URL,
update `DATACHAT_OLLAMA_BASE_URL` in Render (Environment tab) and save. That's it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| First request is slow (~30–60s) | Render free "wakes up" from idle — normal. Keep-warm (Part 7) reduces it. |
| Answers say "busy, try again" | Your PC's Ollama/tunnel isn't reachable. Check the two Part-2 windows are running and the Render `DATACHAT_OLLAMA_BASE_URL` matches the current tunnel URL. |
| `/ready` shows `"degraded"` | The database or cache URL is wrong in Render. Re-check the Neon/Upstash values. |
| Frontend loads but nothing streams | `NEXT_PUBLIC_API_BASE` (Vercel) or `DATACHAT_CORS_ORIGINS` (Render) is wrong — they must point at each other. |
| `401 unauthorized` from Ollama | The Caddy secret and `DATACHAT_OLLAMA_API_KEY` don't match. Make them identical. |

Full reference (every variable, prod notes): **[GOLIVE.md](GOLIVE.md)**.
