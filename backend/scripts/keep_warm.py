"""Keep-warm probe: ping /ready to mitigate free-tier scale-to-zero (NFR-3).

Run on a schedule (cron-job.org or the keep-warm GitHub Action) every ~12 minutes.
Neon resumes in sub-second and the backend stays up, so the first real request
after idle doesn't pay the full cold-start.
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx


async def main() -> int:
    url = os.environ.get("KEEP_WARM_URL", "http://localhost:8000/ready")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=30.0)
    except httpx.HTTPError as exc:
        print(f"[keep-warm] {url} -> error: {exc}")
        return 1
    print(f"[keep-warm] {url} -> {resp.status_code}")
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
