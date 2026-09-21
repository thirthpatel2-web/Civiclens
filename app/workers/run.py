"""Worker / scheduler process entry point.

    python -m app.workers.run worker      # consume Redis jobs
    python -m app.workers.run scheduler   # periodic tasks (SLA scan, RTI reminders, anomalies, ...)
    python -m app.workers.run all         # both in one process (development)
"""

from __future__ import annotations

import logging
import signal
import socket
import sys
import threading
import time

from app.container import build_container
from app.core.config import Settings
from app.core.logging import configure_logging

logger = logging.getLogger("civiclens.workers")


def main(argv: list[str] | None = None) -> int:
    mode = (argv or sys.argv[1:] or ["all"])[0]
    if mode not in ("worker", "scheduler", "all"):
        print(__doc__)
        return 2
    configure_logging()
    container = build_container(Settings.load())
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    worker_id = f"{socket.gethostname()}-{threading.get_native_id()}"

    def worker_loop() -> None:
        while not stop.is_set():
            if container.jobs.run_once(worker_id) is None:
                stop.wait(0.5)

    def scheduler_loop() -> None:
        while not stop.is_set():
            for run in container.scheduler.tick():
                logger.info("scheduled task %s ok=%s %s", run.name, run.ok, run.summary or run.error)
            stop.wait(15.0)

    threads = []
    if mode in ("worker", "all"):
        threads.append(threading.Thread(target=worker_loop, name="worker", daemon=True))
    if mode in ("scheduler", "all"):
        threads.append(threading.Thread(target=scheduler_loop, name="scheduler", daemon=True))
    for t in threads:
        t.start()
    logger.info("started %s (%s)", mode, worker_id)
    while not stop.is_set():
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
