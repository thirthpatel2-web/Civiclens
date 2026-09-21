"""Seed CONFIGURATION data only (departments, cities, routing rules). Never citizens or complaints.

    python scripts/seed.py            # idempotent upsert
SLA policies are deliberately not seeded: they are business policy set by administrators.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings  # noqa: E402
from app.data.seed import load_seed, validate  # noqa: E402
from app.services.ports import CityRecord, DepartmentRecord  # noqa: E402
from app.services.routing_service import RoutingRule  # noqa: E402


def main() -> int:
    seed = load_seed()
    problems = validate(seed)
    if problems:
        print("seed data invalid:", problems)
        return 1
    from app.db.session import make_engine, make_session_factory
    from app.db.uow import SqlUnitOfWork

    uow_factory = lambda: SqlUnitOfWork(make_session_factory(make_engine(Settings.load())))  # noqa: E731
    with uow_factory() as uow:
        for d in seed["departments"]:
            uow.config.save_department(DepartmentRecord(d["code"], d["name"], True))
        for city in seed["cities"]:
            uow.config.save_city(CityRecord(city["code"], city["name"], city["state"], city["lat"], city["lng"]))
        for r in seed["routing_rules"]:
            uow.config.save_routing_rule(RoutingRule(r["id"], r["priority"], r["department_code"], None, frozenset(r["categories"])))
        uow.commit()
    from app.container import build_container

    n = build_container(Settings.load()).emergency.seed_defaults()  # only into an empty table; admins own it afterwards
    print(f"seeded {n} emergency contacts;", end=" ")
    print(f"seeded {len(seed['departments'])} departments, {len(seed['cities'])} cities, {len(seed['routing_rules'])} routing rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
