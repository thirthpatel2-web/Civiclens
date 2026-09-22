"""Attach each government office to its city.

``GovOfficeRecord`` always had a ``city_code`` and the repository always persisted it, but
``AdminService.save_office`` never accepted one, so every office ever created has ``city_code =
NULL``. That makes the Civic Locator unable to group or filter offices by city. The service now
takes the code; this backfills the rows that were written before it did.

A city is assigned only when the city's name appears in the office's name or address. Anything that
does not match is listed and left alone rather than guessed at.

    python scripts/backfill_office_cities.py            # report only
    python scripts/backfill_office_cities.py --apply    # write the changes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.container import build_container  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.transactions import run_in_uow  # noqa: E402

# Cities whose office addresses commonly use another name for the same metro.
ALIASES: dict[str, tuple[str, ...]] = {
    "delhi": ("delhi", "new delhi", "ncr", "noida", "gurugram", "gurgaon", "ghaziabad", "faridabad"),
    "bengaluru": ("bengaluru", "bangalore"),
    "mumbai": ("mumbai", "bombay", "brihanmumbai", "bmc"),
    "chennai": ("chennai", "madras"),
    "kolkata": ("kolkata", "calcutta"),
    "hyderabad": ("hyderabad", "secunderabad", "ghmc"),
    "ahmedabad": ("ahmedabad", "amdavad"),
    "pune": ("pune", "pimpri", "chinchwad", "pmc"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes (default: report only)")
    args = ap.parse_args()

    c = build_container(Settings.load())

    def op(uow):  # type: ignore[no-untyped-def]
        cities = {x.code: x.name for x in uow.config.cities()}
        offices = uow.config.offices()
        planned, unmatched = [], []
        for o in offices:
            if o.city_code:
                continue
            haystack = f"{o.name} {o.address or ''}".lower()
            match = next(
                (code for code in cities if any(a in haystack for a in ALIASES.get(code, (code,)))),
                None,
            )
            (planned.append((o, match)) if match else unmatched.append(o))
        if args.apply:
            for o, code in planned:
                uow.config.save_office(
                    type(o)(o.id, o.name, o.department_code, o.lat, o.lng, o.address, code)
                )
            uow.commit()
        return cities, offices, planned, unmatched

    cities, offices, planned, unmatched = run_in_uow(c, op)
    already = sum(1 for o in offices if o.city_code)
    print(f"offices: {len(offices)} | already linked: {already} | to link: {len(planned)} | unmatched: {len(unmatched)}")
    by_city: dict[str, int] = {}
    for _o, code in planned:
        by_city[code] = by_city.get(code, 0) + 1
    for code, n in sorted(by_city.items()):
        print(f"  {code:<12} {cities[code]:<14} {n}")
    for o in unmatched:
        print(f"  UNMATCHED  {o.name[:70]}")
    print("applied." if args.apply else "dry run - re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
