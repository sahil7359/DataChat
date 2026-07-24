@echo off
REM ============================================================================
REM  Starts your local AI service for DataChat:
REM    Ollama (already running as the Windows tray app)  +  Caddy auth proxy
REM    +  Cloudflare tunnel that gives it a public HTTPS URL.
REM
REM  One-time setup:
REM    1. Install Ollama (ollama.com), Caddy (caddyserver.com), cloudflared.
REM    2. Run once:   ollama pull llama3.2
REM    3. Edit deploy\Caddyfile and set your secret.
REM
REM  Then just double-click this file. Two windows open; keep them running.
REM  Copy the https://<...>.trycloudflare.com URL that cloudflared prints and
REM  set  DATACHAT_OLLAMA_BASE_URL = https://<that-host>/v1  on Render.
REM ============================================================================

echo Pulling the model (skips if already present)...
ollama pull llama3.2

echo Starting the Caddy auth proxy on :11435 ...
start "DataChat Caddy" cmd /k caddy run --config deploy\Caddyfile

echo Starting the Cloudflare tunnel ...
start "DataChat Tunnel" cmd /k cloudflared tunnel --url http://localhost:11435

echo.
echo Both windows are open. Copy the trycloudflare.com URL from the tunnel
echo window into Render as DATACHAT_OLLAMA_BASE_URL (append /v1).
pause
