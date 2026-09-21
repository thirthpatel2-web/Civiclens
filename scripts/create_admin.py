"""Create the FIRST super-admin from the command line (once). Uses the same guarded service as /admin/setup.

    ADMIN_SETUP_TOKEN=... python scripts/create_admin.py --email you@example.org --name "Your Name"
The password is read from a hidden prompt, never from argv.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()
    token = os.environ.get("ADMIN_SETUP_TOKEN", "")
    if not token:
        print("Set ADMIN_SETUP_TOKEN first.")
        return 2
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat: "):
        print("Passwords differ.")
        return 2
    from app.container import build_container
    from app.core.config import Settings
    from app.core.exceptions import CivicLensError

    c = build_container(Settings.load())
    try:
        with c.uow_factory() as uow:
            user = c.auth_for(uow).bootstrap_first_admin(args.email, password, args.name, provided_token=token, expected_token=token)
            uow.commit()
    except CivicLensError as exc:
        print("Refused:", exc.message)
        return 1
    print("Created super-admin", user.id, "- sign in at /admin/login and enrol two-factor authentication.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
