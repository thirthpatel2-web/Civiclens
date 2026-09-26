"""Start the web application (API + UI + WebSocket):  python run.py"""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    if os.environ.get("EMBEDDED_WORKER", "1") != "0":  # one command runs everything; compose sets 0 and uses its worker service
        from app.workers.run import start_embedded

        start_embedded()
    uvicorn.run("app.main:create_app", factory=True, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8080")), proxy_headers=True, forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"))  # noqa: S104
