"""Static link audit: every navigation target in the NiceGUI UI and the React Native app resolves to a real screen.

* NiceGUI: every ``ui.navigate.to(...)`` / ``ui.link(..., target)`` / nav item / redirect literal must match a registered ``@page`` route.
* Mobile (expo-router): every ``router.push/replace(...)``, ``<Link href=...>``, ``<Redirect href=...>`` literal must match a file under mobile/app.

    python scripts/audit_ui_links.py       # exit code 0 = clean
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTERNAL = re.compile(r"^(https?:|tel:|mailto:|/api/|/_nicegui|#)")


def _norm(path: str) -> str:
    path = re.sub(r"\{[^}]*\}", "{}", path).split("?")[0]
    return path.rstrip("/") or "/"


def web_routes() -> set[str]:
    routes: set[str] = set()
    for f in (ROOT / "app/ui/pages").glob("*.py"):
        routes |= {_norm(p) for p in re.findall(r'@page\(c, "([^"]+)"', f.read_text(encoding="utf-8"))}
    return routes


def web_targets() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for f in (ROOT / "app/ui").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        rel = str(f.relative_to(ROOT))
        for m in re.finditer(r'ui\.navigate\.to\(\s*f?"([^"]+)"', text):
            out.append((rel, m.group(1)))
        for m in re.finditer(r'ui\.link\([^,]+,\s*f?"(/[^"]*)"', text):
            out.append((rel, m.group(1)))
        for m in re.finditer(r'\bNavItem\("[\w.]+",\s*"(/[^"]*)"', text):
            out.append((rel, m.group(1)))
        for m in re.finditer(r'return "(/[a-z/]*)"', text) if f.name == "navigation.py" else []:
            out.append((rel, m.group(1)))
    return out


def mobile_routes() -> set[str]:
    base = ROOT / "mobile" / "app"
    routes: set[str] = set()
    for f in base.rglob("*.tsx"):
        parts = [p for p in f.relative_to(base).with_suffix("").parts if not (p.startswith("(") and p.endswith(")")) and p != "_layout"]
        if f.stem == "_layout":
            continue
        r = "/" + "/".join(parts)
        r = re.sub(r"\[[^\]]+\]", "{}", r).replace("/index", "") or "/"
        routes.add(r)
        routes.add("/" + "/".join(f.relative_to(base).with_suffix("").parts).replace("/index", ""))  # group-qualified form: /(tabs)/home
    return {re.sub(r"\[[^\]]+\]", "{}", r) for r in routes}


def mobile_targets() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for f in (ROOT / "mobile").rglob("*.tsx"):
        if "node_modules" in f.parts:
            continue
        text = f.read_text(encoding="utf-8")
        rel = str(f.relative_to(ROOT))
        for m in re.finditer(r"(?:router\.(?:push|replace)|href=\{?|Redirect href=)\(?\s*[\'\"`]([^\'\"`]+)[\'\"`]", text):
            out.append((rel, m.group(1)))
        for m in re.finditer(r"\[\s*'(/[a-z/()-]+)',\s*'[\w.]+',\s*'[^']*'\s*\]", text):  # the "More" menu table
            out.append((rel, m.group(1)))
    return out


def run() -> list[str]:
    problems: list[str] = []
    wr = web_routes()
    for rel, t in web_targets():
        if EXTERNAL.match(t):
            continue
        if _norm(t) not in wr:
            problems.append(f"{rel}: navigates to '{t}' but no page is registered for it")
    mr = mobile_routes()
    for rel, t in mobile_targets():
        if EXTERNAL.match(t) or not t.startswith("/"):
            continue
        n = re.sub(r"\$\{[^}]*\}", "{}", t).split("?")[0]
        if n not in mr:
            problems.append(f"{rel}: navigates to '{t}' but no screen file matches")
    return sorted(set(problems))


if __name__ == "__main__":
    issues = run()
    for i in issues:
        print(i)
    print(f"audit_ui_links: {len(issues)} problem(s); web routes={len(web_routes())}, mobile routes={len(mobile_routes())}, targets checked={len(web_targets()) + len(mobile_targets())}")
    raise SystemExit(1 if issues else 0)
