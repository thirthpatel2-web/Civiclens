"""Static import audit: every ``app.*`` import resolves to a real module/name, no module-level import cycles,
and every third-party import is declared in requirements.txt / requirements-dev.txt.

    python scripts/audit_imports.py        # exit code 0 = clean
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIP_FOR_IMPORT = {"yaml": "pyyaml", "PIL": "pillow", "jose": "python-jose", "googleapiclient": "google-api-python-client", "google": "google-auth", "faster_whisper": "faster-whisper",
                  "pytesseract": "pytesseract", "pyotp": "pyotp", "argon2": "argon2-cffi", "cryptography": "cryptography", "pypdf": "pypdf", "pypdfium2": "pypdfium2", "docx": "python-docx",
                  "reportlab": "reportlab", "nicegui": "nicegui", "fastapi": "fastapi", "uvicorn": "uvicorn", "starlette": "starlette", "sqlalchemy": "sqlalchemy", "alembic": "alembic",
                  "psycopg": "psycopg", "pgvector": "pgvector", "redis": "redis", "httpx": "httpx", "pandas": "pandas", "pyarrow": "pyarrow", "qrcode": "qrcode", "pydantic": "pydantic",
                  "dotenv": "python-dotenv", "sentry_sdk": "sentry-sdk"}  # fmt: skip
OPTIONAL = {"faster_whisper", "pytesseract", "PIL", "googleapiclient", "google", "pandas", "pyarrow", "pypdfium2", "docx", "reportlab", "qrcode", "pyotp", "argon2", "pypdf", "dotenv", "sentry_sdk"}  # imported lazily / in try-blocks


def module_file(mod: str) -> Path | None:
    p = ROOT / Path(*mod.split("."))
    if (p / "__init__.py").exists():
        return p / "__init__.py"
    return p.with_suffix(".py") if p.with_suffix(".py").exists() else None


def top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for n in tree.body:
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(n.name)
        elif isinstance(n, ast.Assign):
            names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            names.add(n.target.id)
        elif isinstance(n, ast.Import | ast.ImportFrom):
            names |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.If | ast.Try):  # conditional definitions
            for sub in ast.walk(n):
                if isinstance(sub, ast.FunctionDef | ast.ClassDef):
                    names.add(sub.name)
                elif isinstance(sub, ast.Assign):
                    names |= {t.id for t in sub.targets if isinstance(t, ast.Name)}
                elif isinstance(sub, ast.Import | ast.ImportFrom):
                    names |= {(a.asname or a.name).split(".")[0] for a in sub.names}
    return names


def declared_requirements() -> set[str]:
    out: set[str] = set()
    for f in ("requirements.txt", "requirements-dev.txt"):
        p = ROOT / f
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*([A-Za-z0-9_.-]+)", line.split("#")[0])
                if m and not line.strip().startswith("-r"):
                    out.add(m.group(1).lower().replace("_", "-"))
    return out


def run() -> list[str]:
    problems: list[str] = []
    reqs = declared_requirements()
    graph: dict[str, set[str]] = {}
    files = [p for d in ("app", "scripts", "tests") for p in (ROOT / d).rglob("*.py")]
    for f in files:
        rel = f.relative_to(ROOT)
        mod = ".".join(rel.with_suffix("").parts).removesuffix(".__init__")
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"{rel}: syntax error {exc}")
            continue
        module_level = {id(n) for n in tree.body} | {id(s) for n in tree.body if isinstance(n, ast.If | ast.Try) for s in ast.walk(n)}
        for node in ast.walk(tree):
            targets: list[tuple[str, list[str]]] = []
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                targets = [(node.module, [a.name for a in node.names])]
            elif isinstance(node, ast.Import):
                targets = [(a.name, []) for a in node.names]
            for target, names in targets:
                top = target.split(".")[0]
                if top in ("app", "tests", "scripts", "tools"):
                    mf = module_file(target)
                    if mf is None:
                        problems.append(f"{rel}:{node.lineno}: unresolved module {target}")
                        continue
                    if id(node) in module_level and top == "app" and mod.startswith("app") and target != mod:
                        graph.setdefault(mod, set()).add(target)
                    if names and mf.name != "__init__.py" or (names and mf.name == "__init__.py"):
                        have = top_level_names(mf)
                        for n in names:
                            if n != "*" and n not in have and module_file(f"{target}.{n}") is None:
                                problems.append(f"{rel}:{node.lineno}: {target} has no name '{n}'")
                elif top not in sys.stdlib_module_names and top != "__future__" and not any((d / f"{top}.py").exists() or (d / top).is_dir() for d in (f.parent, ROOT / "scripts", ROOT / "tools")):  # sibling helper modules are local
                    pip = PIP_FOR_IMPORT.get(top, top).lower().replace("_", "-")
                    if pip not in reqs and top not in ("tests",):
                        problems.append(f"{rel}:{node.lineno}: third-party '{top}' (pip '{pip}') is not declared in requirements*.txt")
    # cycles among module-level imports inside app/
    state: dict[str, int] = {}

    def dfs(m: str, stack: list[str]) -> None:
        state[m] = 1
        for n in graph.get(m, ()):
            if state.get(n) == 1:
                problems.append("import cycle: " + " -> ".join([*stack[stack.index(n) :], n]) if n in stack else f"import cycle at {m} -> {n}")
            elif n not in state:
                dfs(n, [*stack, n])
        state[m] = 2

    for m in list(graph):
        if m not in state:
            dfs(m, [m])
    return sorted(set(problems))


if __name__ == "__main__":
    issues = run()
    for i in issues:
        print(i)
    print(f"audit_imports: {len(issues)} problem(s)")
    raise SystemExit(1 if issues else 0)
