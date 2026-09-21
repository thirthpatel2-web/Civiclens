"""Configuration seed data (departments, cities, routing rules, helplines, languages).

Only configuration is seeded - never citizens or complaints. ``validate`` checks referential
integrity so a bad edit fails fast instead of at routing time.
"""

from __future__ import annotations

from typing import Any

from app.i18n.translator import load_json

FILES = ("departments.json", "cities.json", "routing_rules.json", "national_helplines.json", "supported_languages.json")


def load_seed() -> dict[str, Any]:
    return {name.removesuffix(".json"): load_json(name) for name in FILES}


def validate(seed: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    depts = {d["code"] for d in seed["departments"]}
    if len(depts) != len(seed["departments"]):
        problems.append("duplicate department codes")
    ids = [r["id"] for r in seed["routing_rules"]]
    if len(set(ids)) != len(ids):
        problems.append("duplicate routing rule ids")
    for r in seed["routing_rules"]:
        if r["department_code"] not in depts:
            problems.append(f"rule {r['id']} -> unknown department {r['department_code']}")
    for c in seed["cities"]:
        if not (-90 <= c["lat"] <= 90 and -180 <= c["lng"] <= 180):
            problems.append(f"city {c['code']} has invalid coordinates")
    langs = {x["code"] for x in seed["supported_languages"]}
    if langs != {"en", "hi", "mr", "bn", "ta", "te", "kn"}:
        problems.append(f"unexpected language set {sorted(langs)}")
    for h in seed["national_helplines"]:
        if not h["number"].isdigit():
            problems.append(f"helpline {h['code']} number not numeric")
    return problems
