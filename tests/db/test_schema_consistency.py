"""Schema checks that need no database: the committed migration must match the models.

These verify structure only. That the migrations actually apply to PostgreSQL is
environment-dependent (needs PostgreSQL + pgvector) and is NOT verified here.
"""

import ast
import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_migration", ROOT / "scripts/generate_initial_migration.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_migration"] = mod
    spec.loader.exec_module(mod)
    return mod


class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = load_generator()
        cls.first = (ROOT / "alembic/versions/0001_initial_schema.py").read_text(encoding="utf-8")
        cls.second = (ROOT / "alembic/versions/0004_multilingual_workflow_and_integrations.py").read_text(encoding="utf-8")
        cls.third = (ROOT / "alembic/versions/0005_interoperability_and_learning_loop.py").read_text(encoding="utf-8")
        cls.fourth = (ROOT / "alembic/versions/0006_legal_judgment_fulltext.py").read_text(encoding="utf-8")
        cls.text = cls.first + cls.second + cls.third + cls.fourth  # every model table/column must appear in one of these migrations

    def test_committed_migrations_equal_regenerated_output(self):
        self.assertEqual(self.first, self.gen.emit(), "run: python scripts/generate_initial_migration.py")
        self.assertEqual(self.second, self.gen.emit_second(), "run: python scripts/generate_initial_migration.py")
        self.assertEqual(self.third, self.gen.emit_third(), "run: python scripts/generate_initial_migration.py")
        self.assertEqual(self.fourth, self.gen.emit_fourth(), "run: python scripts/generate_initial_migration.py")

    def test_later_columns_are_added_by_alter_not_baked_into_the_initial_migration(self):
        for table, cols in self.gen.LATER_COLUMNS.items():
            for c in cols:
                self.assertIn(f'op.add_column("{table}", sa.Column("{c}"', self.second)
                self.assertNotRegex(self.first, rf'op.create_table\(\s*"{table}",[\s\S]*?sa.Column\("{c}"[\s\S]*?\n    \)')

    def test_every_model_table_and_column_is_in_the_migration(self):
        tables = self.gen.parse_models()
        specs = self.gen.column_specs(tables)
        self.assertGreaterEqual(len(tables), 42)
        for table, cols in specs.items():
            self.assertIn(f'"{table}"', self.text)
            for c in cols:
                self.assertRegex(self.text, rf'op.create_table\(\s*"{table}",[\s\S]*?sa.Column\("{c["name"]}"')
        for _table, spec in tables.items():
            for e in spec["extras"]:
                if e.func.id == "Index":
                    self.assertIn(ast.unparse(e.args[0]), self.text)

    def test_foreign_keys_reference_existing_tables_created_earlier(self):
        order = re.findall(r'op.create_table\(\s*"(\w+)"', self.text)
        seen = set(re.findall(r'op.create_table\(\s*"(\w+)"', self.first))
        for m in re.finditer(r'op.create_table\(\s*"(\w+)",([\s\S]*?)\n    \)', self.second):
            seen_now = set(seen)
            for ref in re.findall(r'\["(\w+)\.\w+"\]', m.group(2)):
                self.assertTrue(ref in seen_now or ref == m.group(1), f"{m.group(1)} references {ref} before it is created")
            seen.add(m.group(1))
        seen = set()
        for m in re.finditer(r'op.create_table\(\s*"(\w+)",([\s\S]*?)\n    \)', self.text):
            table, body = m.groups()
            for ref in re.findall(r'\["(\w+)\.\w+"\]', body):
                self.assertTrue(ref in seen or ref == table, f"{table} references {ref} before it is created")
            seen.add(table)
        self.assertEqual(len(order), len(set(order)))

    def test_required_domain_tables_exist(self):
        required = {"users", "sessions", "mfa_configs", "departments", "profiles", "complaints", "complaint_events", "complaint_evidence", "routing_rules", "sla_policies", "rti_applications",
                    "documents", "document_chunks", "legal_precedents", "notifications", "notification_preferences", "audit_logs", "government_platforms", "integration_health",
                    "investigations", "anomalies", "analytics_snapshots", "jobs", "consent_records", "ai_conversations", "ai_messages", "drafts", "feedback", "cities", "wards", "civic_services",
                    "government_offices", "voice_transcripts", "duplicate_reviews", "password_reset_tokens", "legal_analyses", "scheduler_state",
                    "workflow_rules", "workflow_executions", "emergency_contacts", "government_submissions", "push_devices",
                    "citizen_external_ids", "integration_exceptions", "external_service_links", "classification_corrections"}
        created = set(re.findall(r'op.create_table\(\s*"(\w+)"', self.text))
        self.assertEqual(required - created, set())

    def test_key_constraints(self):
        for needle in ("uq_users_email", "uq_complaints_reference", "uq_complaints_citizen_client_request", "uq_jobs_idempotency_key", "uq_notifications_user_dedupe_key", "uq_sessions_token_hash", "uq_drafts_user_client_request"):
            self.assertIn(needle, self.text)

    def test_no_create_all_anywhere_in_the_application(self):
        for f in list((ROOT / "app").rglob("*.py")) + list((ROOT / "alembic").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")):
            self.assertNotIn("create_all(", f.read_text(encoding="utf-8"), str(f))

    def test_later_migrations_chain_and_use_configured_dimension(self):
        v = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "alembic/versions").glob("000*.py")}
        self.assertIn('down_revision = "0003"', v["0004_multilingual_workflow_and_integrations.py"])
        self.assertIn('down_revision = None', v["0001_initial_schema.py"])
        self.assertIn('down_revision = "0001"', v["0002_pgvector_embeddings.py"])
        self.assertIn('down_revision = "0002"', v["0003_vector_index.py"])
        self.assertIn("EMBEDDING_DIMENSIONS", v["0002_pgvector_embeddings.py"])
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", v["0002_pgvector_embeddings.py"])
        self.assertIn("hnsw", v["0003_vector_index.py"])
        self.assertIn('down_revision = "0005"', v["0006_legal_judgment_fulltext.py"])
        self.assertIn('down_revision = "0006"', v["0007_legal_judgment_embedding.py"])
        self.assertIn('down_revision = "0007"', v["0008_legal_judgment_vector_index.py"])
        self.assertIn("EMBEDDING_DIMENSIONS", v["0007_legal_judgment_embedding.py"])
        self.assertIn("hnsw", v["0008_legal_judgment_vector_index.py"])

    def test_alembic_env_uses_database_url_not_a_stored_secret(self):
        env = (ROOT / "alembic/env.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("DATABASE_URL"', env)
        self.assertRegex((ROOT / "alembic.ini").read_text(encoding="utf-8"), r"sqlalchemy\.url =\s*\n")


class ModelSourceTests(unittest.TestCase):
    def test_model_modules_parse_and_every_model_has_a_tablename(self):
        for f in (ROOT / "app/db/models").glob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and any(getattr(b, "id", "") == "Base" for b in n.bases)]:
                self.assertTrue(any(isinstance(s, ast.Assign) and s.targets[0].id == "__tablename__" for s in cls.body), cls.name)

    def test_repositories_cover_every_port(self):
        from app.services import ports

        port_names = {n for n, v in vars(ports).items() if isinstance(v, type) and n.endswith("Repository")}
        impl_src = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "app/db/repositories").glob("*.py"))
        for port in sorted(port_names):
            # each Protocol's methods must exist on some SQL repository
            methods = [m for m in vars(getattr(ports, port)) if not m.startswith("_")]
            for m in methods:
                self.assertRegex(impl_src, rf"def {m}\(", f"{port}.{m} has no SQL implementation")


if __name__ == "__main__":
    unittest.main()
