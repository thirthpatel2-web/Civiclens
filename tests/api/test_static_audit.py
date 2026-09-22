"""Static completeness audit of the API and UI (no framework needed): parses the source with ``ast``.

Answers, mechanically: is every route protected/authorised? are there GET routes under RAG? does every
nav item have a page? does every UI string key exist? does any button lack a handler? is there any JS?
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "app/api/v1"
METHODS = {"get", "post", "put", "delete", "patch"}
PUBLIC = {("auth", "register"), ("auth", "login"), ("auth", "mobile_login"), ("auth", "admin_login"), ("auth", "forgot"), ("auth", "reset"), ("auth", "bootstrap"), ("misc", "health"), ("misc", "ready"), ("misc", "helplines")}


def parse_routes():
    routes = []
    for f in sorted(API.glob("*.py")):
        if f.stem in ("__init__", "router"):
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        prefixes, guards = {}, set()
        for n in tree.body:
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                fn = n.value.func
                name = getattr(fn, "id", "")
                if name == "APIRouter":
                    prefix = next((k.value.value for k in n.value.keywords if k.arg == "prefix"), "")
                    prefixes[n.targets[0].id] = prefix
                if name == "Depends" and "guard(" in ast.unparse(n.value):
                    guards.add(n.targets[0].id)
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                for d in n.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in METHODS and isinstance(d.func.value, ast.Name) and d.func.value.id in prefixes:
                        args = ast.unparse(n.args)
                        protected = "guard(" in args or "get_ctx" in args or any(re.search(rf"\b{g}\b", args) for g in guards)
                        path = prefixes[d.func.value.id] + (d.args[0].value if d.args else "")
                        routes.append({"file": f.stem, "func": n.name, "method": d.func.attr, "path": path, "protected": protected, "args": args, "router": d.func.value.id})
    return routes


class ApiAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = parse_routes()

    def test_route_count_and_required_prefixes(self):
        self.assertGreaterEqual(len(self.routes), 100)
        prefixes = {r["path"].split("/")[1] for r in self.routes}
        for p in ("auth", "complaints", "rti", "legal", "assistant", "documents", "voice", "gis", "officer", "admin", "notifications", "analytics", "integrations", "profiles", "monitoring", "consent", "rag", "dashboards"):
            self.assertIn(p, prefixes)

    def test_every_route_is_authenticated_except_the_explicit_public_list(self):
        unprotected = {(r["file"], r["func"]) for r in self.routes if not r["protected"]}
        self.assertEqual(unprotected, PUBLIC)

    def test_rag_surface_has_no_get_endpoints(self):
        for r in self.routes:
            if r["file"] in ("assistant", "rag") or r["path"] in ("/documents/search", "/legal/analyze"):
                self.assertNotEqual(r["method"], "get", r)
        rag_paths = {(r["method"], r["path"]) for r in self.routes}
        for needed in (("post", "/rag/query"), ("post", "/rag/retrieve"), ("post", "/assistant/ask"), ("post", "/assistant/chat"), ("post", "/documents/search")):
            self.assertIn(needed, rag_paths)

    def test_admin_routes_require_admin_permissions(self):
        for r in self.routes:
            if r["file"] == "admin":
                self.assertTrue("Permission.ADMIN" in r["args"] or re.search(r"\b(ADM|DEP)\b", r["args"]), r)

    def test_officer_routes_require_officer_permissions(self):
        for r in self.routes:
            if r["file"] == "officer":
                self.assertTrue(re.search(r"Permission\.(COMPLAINT|INVESTIGATION|DUPLICATE)|\b(READ|STATUS|FIELD|ASSIGN|INVEST|DUP)\b", r["args"]), r)

    def test_registration_cannot_carry_a_role(self):
        src = (ROOT / "app/schemas/api.py").read_text(encoding="utf-8")
        body = re.search(r"class RegisterBody\(Strict\):([\s\S]*?)\n\n\n", src).group(1)
        self.assertNotIn("role", body)
        self.assertIn('extra="forbid"', src)

    def test_no_business_logic_loops_in_route_functions(self):
        for f in API.glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]:
                if any(isinstance(d, ast.Call) and getattr(getattr(d.func, "value", None), "id", "") in ("router", "notifications", "profiles", "consent", "gis", "dashboards", "analytics", "integrations", "monitoring") for d in fn.decorator_list):
                    loops = [n for n in ast.walk(fn) if isinstance(n, ast.For | ast.While) and not isinstance(n, ast.ListComp)]
                    self.assertEqual(loops, [], f"{f.stem}.{fn.name} contains a loop; move it into a service")

    def test_session_cookie_flags(self):
        src = (API / "auth.py").read_text(encoding="utf-8")
        self.assertIn("httponly=True", src)
        self.assertIn('samesite="lax"', src)
        self.assertIn("secure=c.settings.is_production", src)

    def test_login_failure_paths_persist_their_audit_rows(self):
        src = (API / "auth.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(src.count("commit_on_error=True"), 6)


class UiAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {f.stem: f.read_text(encoding="utf-8") for f in (ROOT / "app/ui/pages").glob("*.py") if f.stem != "__init__"}
        cls.pages = set()
        for src in cls.files.values():
            cls.pages |= set(re.findall(r'@page\(c, "([^"]+)"', src))
        cls.pages_norm = {re.sub(r"/\{\w+\}", "", p) or "/" for p in cls.pages}

    def test_every_navigation_route_has_a_page(self):
        from app.ui.navigation import NAVIGATION

        for g in NAVIGATION:
            for item in g.items:
                self.assertIn(item.route, self.pages_norm, item)

    def test_required_pages_exist(self):
        for p in ("/", "/login", "/register", "/reset-password", "/onboarding", "/dashboard", "/report", "/rti", "/legal", "/copilot", "/gis", "/grievances", "/emergency", "/profile", "/settings", "/notifications", "/security", "/documents",
                  "/admin/login", "/admin/setup", "/admin", "/admin/users", "/admin/departments", "/admin/wards", "/admin/services", "/admin/routing-rules", "/admin/sla", "/admin/integrations", "/admin/audit", "/admin/analytics",
                  "/admin/anomalies", "/admin/investigations", "/officer", "/officer/queue", "/officer/complaints", "/officer/investigations"):  # fmt: skip
            self.assertIn(p, self.pages_norm, p)

    def test_role_gating_declared_for_staff_and_admin_pages(self):
        for src in (self.files["staff"], self.files["admin"]):
            for m in re.finditer(r'@page\(c, "([^"]+)"[^)]*\)', src):
                self.assertIn("roles=", m.group(0), m.group(1))

    def test_every_ui_string_key_exists_in_the_dictionaries(self):
        from app.i18n.ui_text import UiText

        ui_text = UiText.load()
        known = set(ui_text.extras["en"]) | set(ui_text.base._tr["en"])
        used = set()
        for src in list(self.files.values()) + [(ROOT / "app/ui/base.py").read_text(encoding="utf-8"), (ROOT / "app/ui/navigation.py").read_text(encoding="utf-8")]:
            used |= set(re.findall(r'tr\(c, "([\w.]+)"\)', src))
            used |= set(re.findall(r'NavItem\("([\w.]+)"', src)) | set(re.findall(r'NavGroup\("([\w.]+)"', src))
        self.assertGreater(len(used), 60)
        self.assertEqual(sorted(k for k in used if k not in known), [])

    def test_no_javascript_no_dead_buttons_no_placeholders(self):
        # The only sanctioned JavaScript in the web UI is two thin bridges to browser hardware APIs
        # that NiceGUI has no Python equivalent for: MediaRecorder (voice input) and
        # navigator.geolocation ("use my location"). Both only relay one raw event back to Python
        # via emitEvent(); every decision is still made in Python. Anything else stays banned, and
        # a stray fetch/XHR/eval/innerHTML alongside a legitimate bridge is still caught below.
        BANNED_EVEN_NEAR_A_BRIDGE = ("fetch(", "XMLHttpRequest", "eval(", "innerHTML", "document.write", "add_head_html")
        for f in list((ROOT / "app/ui").rglob("*.py")):
            src = f.read_text(encoding="utf-8")
            self.assertNotIn("add_head_html", src, f)
            if "run_javascript" in src or "add_body_html" in src:
                self.assertTrue(("MediaRecorder" in src and "getUserMedia" in src) or "navigator.geolocation" in src, f"{f.name}: JS present without a recognised hardware-API bridge")
                for banned in BANNED_EVEN_NEAR_A_BRIDGE:
                    self.assertNotIn(banned, src, f"{f.name}: disallowed JavaScript pattern {banned!r}")
            tree = ast.parse(src)
            in_with = {id(x) for w in ast.walk(tree) if isinstance(w, ast.With) for i in w.items for x in ast.walk(i.context_expr)}  # a button used as a menu trigger
            # A button can also get its handler after construction - `mic = ui.button(...)` then
            # later `mic.on_click(fn)` or `mic.on("click", fn)` - which is the only way to wire one
            # up when the handler closes over the button variable itself (see the voice mic toggle).
            deferred_bound = {
                n.func.value.id
                for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                and (n.func.attr == "on_click" or (n.func.attr == "on" and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "click"))
            }
            # `mic = ui.button(...).props(...).style(...)` assigns the *outermost* chained call to
            # `mic`, not the ui.button() call itself, so every Call in the chain is mapped to the
            # assigned name, not just the leaf.
            assign_targets: dict[int, str] = {}
            for n in ast.walk(tree):
                if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                    cur = n.value
                    while isinstance(cur, ast.Call):
                        assign_targets[id(cur)] = n.targets[0].id
                        cur = cur.func.value if isinstance(cur.func, ast.Attribute) else None
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and ast.unparse(n.func) == "ui.button" and id(n) not in in_with:
                    name = assign_targets.get(id(n))
                    has_handler = any(k.arg == "on_click" for k in n.keywords) or (name is not None and name in deferred_bound)
                    self.assertTrue(has_handler, f"{f.name}: ui.button without a handler: {ast.unparse(n)[:80]}")
        # The ONLY JavaScript/TypeScript allowed is the React Native + Expo client under mobile/; the backend and the web UI stay Python.
        # Third-party packages (.venv, node_modules) are excluded: they are dependencies, not code this project wrote.
        excluded_roots = {"mobile", ".venv", "venv", "node_modules", ".git"}
        js = [p for p in ROOT.rglob("*") if (p.suffix in (".js", ".ts", ".tsx", ".jsx", ".vue") or p.name in ("package.json", "node_modules")) and not excluded_roots & set(p.relative_to(ROOT).parts[:1])]
        self.assertEqual(js, [])
        self.assertFalse((ROOT / "mobile" / "server").exists(), "no second (Node) backend")
        import json

        pkg = json.loads((ROOT / "mobile" / "package.json").read_text(encoding="utf-8"))
        deps = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
        self.assertEqual(deps & {"express", "koa", "fastify", "pg", "mongoose", "bullmq", "ioredis", "sequelize", "prisma", "@nestjs/core"}, set(), "the mobile app must not bundle backend frameworks")

    def test_pages_call_services_not_raw_sql(self):
        for name, src in self.files.items():
            self.assertNotRegex(src, r"\.execute\(|from sqlalchemy", name)

    def test_language_selector_and_shell_features_present(self):
        base = (ROOT / "app/ui/base.py").read_text(encoding="utf-8")
        for needle in ("lang_sel", "ui.left_drawer", "ui.header", "ws.connect", "notifications.unread_count", "sign_out", "ui.timer"):
            self.assertIn(needle, base)


class RepositoryWiringTests(unittest.TestCase):
    def test_no_in_memory_repositories_in_production_code(self):
        for f in (ROOT / "app").rglob("*.py"):
            self.assertNotRegex(f.read_text(encoding="utf-8"), r"class Mem\w*(Repo|Uow|UnitOfWork)", str(f))

    def test_container_uses_sql_unit_of_work_in_production_builder(self):
        src = (ROOT / "app/container.py").read_text(encoding="utf-8")
        self.assertIn("SqlUnitOfWork", src)
        self.assertIn("Argon2Hasher", src)
        self.assertIn("PyOtpEngine", src)

    def test_app_container_construction_never_relies_on_optional_field_position(self):
        """Regression guard: AppContainer's optional fields (llm, embedder, ocr, ollama, vector_index,
        ...) have all shifted position at least once as the dataclass grew, and a stale positional
        call silently posts each value one field too early/late - construction succeeds, every field
        is *some* object, and nothing raises. That exact bug (ollama's OllamaClient landing in the
        `ocr` slot, PgVectorSearcher landing in `ollama`, `vector_index` silently staying None) broke
        semantic search in production with zero test failures until it was caught by hand. So: only
        the fields with no default may be passed positionally to AppContainer(...); anything after
        the first defaulted field must be a keyword, in every call site, forever."""
        import ast

        tree = ast.parse((ROOT / "app/container.py").read_text(encoding="utf-8"))
        class_def = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "AppContainer")
        fields = [n.target.id for n in class_def.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
        first_defaulted = next(n.target.id for n in class_def.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None)
        max_bare_positional = fields.index(first_defaulted)

        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "AppContainer"]
        self.assertTrue(calls, "no AppContainer(...) construction found")
        for call in calls:
            self.assertLessEqual(len(call.args), max_bare_positional,
                                  f"AppContainer(...) at line {call.lineno} passes {len(call.args)} positional args, "
                                  f"but only the first {max_bare_positional} fields ({', '.join(fields[:max_bare_positional])}) have no default - "
                                  "every field from there on must be passed as a keyword or it can silently land in the wrong slot.")


if __name__ == "__main__":
    unittest.main()
