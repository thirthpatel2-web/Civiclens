"""Runs the repository audits as tests (import resolution, navigation targets, security patterns) and proves they can fail."""

import importlib.util
import re
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ImportAuditTests(unittest.TestCase):
    def test_every_internal_import_resolves_no_cycles_and_all_dependencies_are_declared(self):
        self.assertEqual(load("audit_imports").run(), [])

    def test_the_audit_detects_a_broken_import_and_an_undeclared_dependency(self):
        mod = load("audit_imports")
        bad = ROOT / "app" / "_audit_probe.py"
        bad.write_text("from app.core.config import DoesNotExist\nfrom app.nope import x\nimport left_pad_py\n")
        try:
            problems = "\n".join(mod.run())
        finally:
            bad.unlink()
        self.assertIn("has no name 'DoesNotExist'", problems)
        self.assertIn("unresolved module app.nope", problems)
        self.assertIn("left_pad_py", problems)


class LinkAuditTests(unittest.TestCase):
    def test_every_web_and_mobile_navigation_target_exists(self):
        self.assertEqual(load("audit_ui_links").run(), [])

    def test_the_audit_detects_dead_links_on_both_platforms(self):
        mod = load("audit_ui_links")
        with mock.patch.object(mod, "web_targets", lambda: [("x.py", "/no-such-page")]), mock.patch.object(mod, "mobile_targets", lambda: [("x.tsx", "/no-such-screen"), ("y.tsx", "/complaint/${id}")]):
            problems = mod.run()
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("/no-such-page" in p for p in problems) and any("/no-such-screen" in p for p in problems))

    def test_parameterised_routes_match(self):
        mod = load("audit_ui_links")
        self.assertIn("/grievances/{}", mod.web_routes())
        self.assertIn("/complaint/{}", mod.mobile_routes())
        self.assertIn("/home", mod.mobile_routes())


DANGEROUS = [
    (r"\beval\(|\bexec\(", "eval/exec"),
    (r"pickle\.loads?\(", "pickle deserialisation"),
    (r"subprocess\.[a-z_]+\([^)]*shell\s*=\s*True", "shell=True"),
    (r"yaml\.load\((?![^)]*Loader)", "unsafe yaml.load"),
    (r"verify\s*=\s*False", "TLS verification disabled"),
    (r"\bmd5\(|hashlib\.sha1\(", "weak hash for security use"),
    (r"random\.(random|randint|choice)\(", "non-cryptographic RNG (use secrets)"),
    (r"-----BEGIN (RSA |EC )?PRIVATE KEY-----", "embedded private key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"(?i)(api[_-]?key|secret|passw(or)?d|token)\s*=\s*[\"'][A-Za-z0-9+/_\-]{16,}[\"']", "hard-coded credential"),
    (r"debug\s*=\s*True", "debug mode enabled"),
    # CORSMiddleware itself is not banned: the Expo web dev build is a real, non-production cross-origin
    # client. What's banned is the specific patterns that would make it insecure - a wildcard/unrestricted
    # origin, or enabling credentialed CORS (this API is Bearer-token only; credentialed CORS is for
    # cookie-based auth, which this app never sends cross-origin).
    (r"allow_origins\s*=\s*\[\s*[\"']\*", "wildcard CORS"),
    (r"allow_origin_regex\s*=\s*[\"']\.\*[\"']", "unrestricted CORS origin regex"),
    (r"allow_credentials\s*=\s*True", "credentialed CORS (this API is Bearer-token only)"),
    (r"innerHTML|dangerouslySetInnerHTML|ui\.html\(|ui\.markdown\([^)]*sanitize\s*=\s*False", "raw HTML injection surface"),
]


class SecurityPatternTests(unittest.TestCase):
    def test_no_dangerous_patterns_in_application_code(self):
        hits = []
        for base in (ROOT / "app", ROOT / "scripts", ROOT / "classic-app" / "src", ROOT / "classic-app" / "app"):
            for f in base.rglob("*"):
                if f.suffix not in (".py", ".ts", ".tsx") or "node_modules" in f.parts or f.name == "test_audits.py":
                    continue
                text = f.read_text(encoding="utf-8")
                for pat, why in DANGEROUS:
                    for m in re.finditer(pat, text):
                        line = text.count("\n", 0, m.start()) + 1
                        hits.append(f"{f.relative_to(ROOT)}:{line}: {why}")
        self.assertEqual(hits, [])

    def test_sql_is_only_built_by_the_orm_and_the_two_fixed_statements(self):
        raw = []
        for f in (ROOT / "app").rglob("*.py"):
            for m in re.finditer(r"(?:\.execute|(?<![\w.])text)\(\s*f[\"']", f.read_text(encoding="utf-8")):
                raw.append(f"{f.relative_to(ROOT)}:{f.read_text(encoding="utf-8").count(chr(10), 0, m.start()) + 1}")
        self.assertEqual(raw, [], "f-string SQL is forbidden")

    def test_secrets_never_appear_in_api_responses_or_serialisation(self):
        from app.api.serialize import _HIDE

        for field in ("password_hash", "secret_encrypted", "backup_code_hashes", "token_hash"):
            self.assertIn(field, _HIDE)

    def test_the_session_token_is_never_placed_in_a_web_response_body(self):
        src = (ROOT / "app/api/v1/auth.py").read_text(encoding="utf-8")
        self.assertEqual(src.count('"session_token"'), 1)  # only the mobile endpoint returns it
        self.assertIn("mobile_login", src[src.index('"session_token"') - 900 : src.index('"session_token"')])

    def test_mobile_stores_the_token_only_in_the_secure_store(self):
        for f in (ROOT / "classic-app" / "src").rglob("*.ts*"):
            text = f.read_text(encoding="utf-8")
            if re.search(r"from ['\"]@react-native-async-storage", text):  # files that really use AsyncStorage
                self.assertNotRegex(text, r"setItem\([^)]*token", f)
                self.assertNotIn("session.token", text, f)
        self.assertIn("expo-secure-store", (ROOT / "classic-app/src/auth/session.ts").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
