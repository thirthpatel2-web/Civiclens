"""Create the demo accounts that docs/DEMO_GUIDE.md and the demo video use, on a fresh install.

    python scripts/seed_demo.py            # after `alembic upgrade head` and `python scripts/seed.py`

Idempotent: an account that already exists is left exactly as it is. Every account gets the password in
DEMO_PASSWORD (default: the one printed in DEMO_GUIDE.md). Priya and Arjun carry the mobile numbers of the
demo Revenue / Seva Setu records, so the consent requests in the Interop Gateway reach their own app.
These are demo accounts for a demo deployment - do not run this against a real citizen database.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CITIZENS = (
    # email, name, mobile, city
    ("demo.priya@example.com", "Priya Deshmukh", "9876543210", "Pune"),
    ("demo.arjun@example.com", "Arjun Patil", "9822011223", "Mumbai"),
)
STAFF = (
    # email, name, role, department
    ("demo.admin@example.com", "Anita Rao (Admin)", "admin", None),
    ("demo.integration@example.com", "Integration Admin (Demo)", "integration_admin", None),
    ("demo.auditor@example.com", "Auditor (Demo)", "auditor", None),
    ("demo.officer@example.com", "Ravi Kumar (Roads Officer)", "officer", "roads"),
    ("demo.water@example.com", "Sunita Joshi (Water Officer)", "officer", "water"),
    ("demo.sanitation@example.com", "Imran Shaikh (Sanitation Officer)", "officer", "sanitation"),
    ("demo.electricity@example.com", "Meera Kulkarni (Electricity Officer)", "officer", "electricity"),
    ("demo.drainage@example.com", "Rahul Desai (Drainage Officer)", "officer", "drainage"),
    ("demo.encroachment@example.com", "Kavya Nair (Encroachment Officer)", "officer", "encroachment"),
)
CONSENTS = ("privacy_policy", "ai_processing", "data_sharing_government", "document_storage")
# a few complaints the demo walks through (only filed for a citizen account this script just created)
SAMPLES = {
    "demo.priya@example.com": (
        ("Drain overflowing on FC Road after every rain", "The storm drain near Goodluck Chowk on FC Road overflows every time it rains. Dirty water floods the footpath and enters the shops.", "Goodluck Chowk, FC Road, Pune", True),
        ("Garbage not collected for five days near Aundh market", "The garbage bins next to Aundh vegetable market have not been emptied for five days. Waste is spilling onto the road.", "Aundh market, Pune", False),
    ),
    "demo.arjun@example.com": (
        ("Divider lamps off on Warje bridge road", "Dark road at night near Warje bridge - the lamps on the divider are off. Two-wheelers can't see the divider.", "Warje bridge service road, Pune", False),
    ),
}


def main() -> int:
    from app.container import build_container
    from app.core.authorization import AuthContext, Role
    from app.core.config import Settings
    from app.services.auth_service import UserRecord
    from app.services.complaint_service import ComplaintInput

    settings = Settings.load()
    password = os.environ.get("DEMO_PASSWORD", "CivicLens#Demo2026")
    c = build_container(settings)
    made, kept = [], []
    with c.uow_factory() as uow:
        departments = {d.code for d in uow.config.departments()}
    missing = {d for *_, d in STAFF if d} - departments
    if missing:
        print(f"Run `python scripts/seed.py` first - missing departments: {sorted(missing)}")
        return 2
    for email, name, role, dept in STAFF:
        with c.uow_factory() as uow:
            if uow.users.get_by_email(email):
                kept.append(email)
                continue
            uow.users.add(UserRecord(id=str(uuid.uuid4()), email=email, password_hash=c.hasher.hash(password), full_name=name, role=Role(role), department_id=dept))
            uow.commit()
            made.append(email)
    for email, name, mobile, city in CITIZENS:
        with c.uow_factory() as uow:
            if uow.users.get_by_email(email):
                kept.append(email)
                continue
            user = c.auth_for(uow).register(email, password, name)
            uow.commit()
        ctx = AuthContext(user.id, Role.CITIZEN, None, False)
        c.profiles.update(ctx, full_name=name, phone=mobile, city=city, language="en", complete_onboarding=True)
        for purpose in CONSENTS:
            c.profiles.set_consent(ctx, purpose, True)
        for title, text, address, escalate in SAMPLES.get(email, ()):
            r = c.complaints.create(ctx, ComplaintInput(title=title, description=text, address=address, city="pune"))
            if escalate:  # the demo drafts an RTI from an escalated complaint
                cm = r.complaint
                with c.uow_factory() as uow:
                    officer = next((u for u in uow.officers.officer_ids_for_department(cm.department_code or "")), None)
                if officer:
                    c.officer.escalate(AuthContext(officer, Role.OFFICER, cm.department_code, False), cm.id, "Needs stormwater capital works approval from the zonal office.")
        made.append(email)
    print(f"created {len(made)} demo account(s); {len(kept)} already existed")
    for e in made:
        print("  +", e)
    print("Password for every new account: the value of DEMO_PASSWORD" + (" (default CivicLens#Demo2026)." if "DEMO_PASSWORD" not in os.environ else "."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
