"""Generate ``alembic/versions/0001_initial_schema.py`` from the SQLAlchemy model *source* (stdlib ``ast``).

Why a generator: the migration must be an explicit, reviewable list of ``op.create_table`` calls
(not ``metadata.create_all``) yet must never drift from the models. tests/db/test_schema_consistency.py
re-runs this generator and fails if the committed migration differs from what the models imply.
The pgvector column/index live in migrations 0002/0003 because their dimension is deployment config.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_FILES = ["identity", "reference", "complaints", "content", "ops", "interop"]
INITIAL_TABLES = frozenset(['ai_conversations', 'ai_messages', 'analytics_snapshots', 'anomalies', 'audit_logs', 'cities', 'civic_services', 'complaint_events', 'complaint_evidence', 'complaints', 'consent_records', 'departments', 'document_chunks', 'documents', 'drafts', 'duplicate_reviews', 'feedback', 'government_offices', 'government_platforms', 'integration_health', 'investigations', 'jobs', 'legal_analyses', 'legal_precedents', 'mfa_configs', 'notification_preferences', 'notifications', 'password_reset_tokens', 'profiles', 'routing_rules', 'rti_applications', 'scheduler_state', 'sessions', 'sla_policies', 'users', 'voice_transcripts', 'wards'])
# Tables added by migration 0004; frozen the same way as INITIAL_TABLES so a later addition (0005+)
# can never silently get folded back into an already-committed migration.
SECOND_TABLES = frozenset(['emergency_contacts', 'government_submissions', 'push_devices', 'workflow_rules', 'workflow_executions'])
# Tables added by migration 0005; frozen the same way, so a later addition (0006+) can never
# silently get folded back into it either.
THIRD_TABLES = frozenset(['citizen_external_ids', 'classification_corrections', 'external_service_links', 'integration_exceptions'])
# Columns added after the initial release; emitted as ALTERs in migration 0004, never in 0001.
LATER_COLUMNS = {
    "complaints": ["detected_language", "translated_text", "translated_language", "translation_provider", "input_method", "voice_id"],
    "voice_transcripts": ["detected_by", "confidence", "script_ok", "warnings"],
    "sessions": ["kind"],
    "jobs": ["started_at", "finished_at"],
}
# Columns whose TYPE (not existence) changed after the initial release: migration 0001 must keep
# emitting the original type (what actually shipped); the model and a later ALTER (migration 0009)
# reflect the widened type. Same spirit as LATER_COLUMNS, but for a width change, not a new column.
LATER_COLUMN_TYPES = {
    "legal_precedents": {"disposal": "sa.String(80)"},
}
SECOND_TARGET = "0004_multilingual_workflow_and_integrations.py"
THIRD_TARGET = "0005_interoperability_and_learning_loop.py"
FOURTH_TARGET = "0006_legal_judgment_fulltext.py"
SIMPLE = {"Boolean": "sa.Boolean()", "Integer": "sa.Integer()", "Float": "sa.Float()", "Text": "sa.Text()", "BigInteger": "sa.BigInteger()", "Date": "sa.Date()", "JSONB": "postgresql.JSONB(astext_type=sa.Text())"}


def src(node: ast.AST) -> str:
    return ast.unparse(node)


def type_of(call: ast.Call | None, annotation: ast.AST, fk_types: dict[str, str]) -> str | None:
    if call is not None and call.args:
        a0 = call.args[0]
        if isinstance(a0, ast.Call) and isinstance(a0.func, ast.Name):
            name = a0.func.id
            if name == "ForeignKey":
                return fk_types.get(ast.literal_eval(a0.args[0]))
            if name == "String":
                return f"sa.String({', '.join(src(x) for x in a0.args)})"
            if name == "Vector":
                return None
        if isinstance(a0, ast.Name) and a0.id in SIMPLE:
            return SIMPLE[a0.id]
        if isinstance(a0, ast.Constant) and isinstance(a0.value, str) and len(call.args) > 1:  # mapped_column("name", TYPE, ...)
            a1 = call.args[1]
            if isinstance(a1, ast.Name) and a1.id in SIMPLE:
                return SIMPLE[a1.id]
    ann = src(annotation)
    for py, sql in (("bool", "sa.Boolean()"), ("int", "sa.Integer()"), ("float", "sa.Float()"), ("date", "sa.Date()"), ("datetime", "sa.DateTime(timezone=True)")):
        if ann.startswith(f"Mapped[{py}"):
            return sql
    return None


def kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def parse_models() -> dict[str, dict]:
    tables: dict[str, dict] = {}
    for f in MODEL_FILES:
        tree = ast.parse((ROOT / "app/db/models" / f"{f}.py").read_text(encoding="utf-8"))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            table = next((ast.literal_eval(s.value) for s in cls.body if isinstance(s, ast.Assign) and s.targets[0].id == "__tablename__"), None)  # type: ignore[attr-defined]
            if table is None:
                continue
            cols, extras = [], []
            for s in cls.body:
                if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name) and isinstance(s.value, ast.Call):
                    cols.append((s.target.id, s.annotation, s.value))
                elif isinstance(s, ast.Assign) and s.targets[0].id == "__table_args__":  # type: ignore[attr-defined]
                    extras = list(s.value.elts) if isinstance(s.value, ast.Tuple) else [s.value]
            tables[table] = {"cols": cols, "extras": extras}
    return tables


def column_specs(tables: dict[str, dict]) -> dict[str, list[dict]]:
    """Two passes so FK columns inherit the referenced column's type."""
    specs: dict[str, list[dict]] = {t: [] for t in tables}
    types: dict[str, str] = {}
    pending = list(tables)
    for _ in range(len(tables) + 1):
        for t in list(pending):
            ok = True
            out = []
            for attr, ann, call in tables[t]["cols"]:
                helper = call.func.id if isinstance(call.func, ast.Name) else ""
                name = attr
                if helper == "mapped_column" and call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                    name = call.args[0].value
                fk = next((a for a in ([call.args[0]] if call.args else []) if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "ForeignKey"), None)
                spec: dict = {"name": name, "fk": None, "pk": False, "server_default": None}
                if helper == "uuid_pk":
                    spec.update(type="sa.Uuid(as_uuid=False)", nullable=False, pk=True)
                elif helper == "created_at":
                    spec.update(type="sa.DateTime(timezone=True)", nullable=False, server_default='sa.text("now()")')
                elif helper == "tstz":
                    nullable = True
                    if call.args:
                        nullable = bool(ast.literal_eval(call.args[0]))
                    elif kw(call, "nullable") is not None:
                        nullable = bool(ast.literal_eval(kw(call, "nullable")))  # type: ignore[arg-type]
                    spec.update(type="sa.DateTime(timezone=True)", nullable=nullable)
                elif helper == "jsonb":
                    spec.update(type="postgresql.JSONB(astext_type=sa.Text())", nullable=False)
                else:
                    typ = type_of(call, ann, types)
                    if typ is None and any(isinstance(x, ast.Call) and getattr(x.func, "id", "") == "Vector" for x in call.args):
                        continue  # pgvector column: created by migration 0002
                    if fk is not None:
                        ref = ast.literal_eval(fk.args[0])
                        typ = types.get(ref)
                        spec["fk"] = (ref, src(kw(fk, "ondelete")) if kw(fk, "ondelete") is not None else None)
                    if typ is None:
                        ok = False
                        break
                    nn = kw(call, "nullable")
                    optional = "None" in src(ann)
                    pk = kw(call, "primary_key") is not None and ast.literal_eval(kw(call, "primary_key"))  # type: ignore[arg-type]
                    spec.update(type=typ, nullable=(ast.literal_eval(nn) if nn is not None else optional) and not pk, pk=bool(pk))
                    sd = kw(call, "server_default")
                    if sd is not None:
                        spec["server_default"] = f"sa.{ast.unparse(sd)}" if isinstance(sd, ast.Call) else ast.unparse(sd)
                    if kw(call, "autoincrement") is not None:
                        spec["autoincrement"] = True
                if helper in ("uuid_pk", "created_at", "tstz", "jsonb") and fk is None:
                    pass
                out.append(spec)
                types[f"{t}.{name}"] = spec["type"]
            if ok:
                specs[t] = out
                pending.remove(t)
    if pending:
        raise SystemExit(f"could not resolve column types for {pending}")
    return specs


def order(tables: dict[str, dict], specs: dict[str, list[dict]]) -> list[str]:
    deps = {t: {c["fk"][0].split(".")[0] for c in specs[t] if c["fk"]} - {t} for t in tables}
    out: list[str] = []
    while len(out) < len(tables):
        ready = sorted(t for t in tables if t not in out and deps[t] <= set(out))
        if not ready:
            raise SystemExit("cyclic foreign keys")
        out.append(ready[0])
    return out


def _table_block(t: str, specs: dict[str, list[dict]], tables: dict[str, dict], skip_cols: set[str], type_overrides: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    lines = [f'    op.create_table(\n        "{t}",']
    idx: list[str] = []
    pks = []
    overrides = type_overrides or {}
    cols = [c for c in specs[t] if c["name"] not in skip_cols]
    for c in cols:
        col_type = overrides.get(c["name"], c["type"])
        args = [f'"{c["name"]}"', col_type, f"nullable={c['nullable']}"]
        if c["server_default"]:
            args.append(f"server_default={c['server_default']}")
        if c.get("autoincrement"):
            args.append("autoincrement=True")
        lines.append(f"        sa.Column({', '.join(args)}),")
        if c["pk"]:
            pks.append(c["name"])
    lines.append(f'        sa.PrimaryKeyConstraint({", ".join(repr(p) for p in pks)}, name="pk_{t}"),')
    for c in cols:
        if c["fk"]:
            ref, ondel = c["fk"]
            extra = f", ondelete={ondel}" if ondel else ""
            lines.append(f'        sa.ForeignKeyConstraint(["{c["name"]}"], ["{ref}"], name="fk_{t}_{c["name"]}_{ref.split(".")[0]}"{extra}),')
    for e in tables[t]["extras"]:
        name = e.func.id  # type: ignore[attr-defined]
        if name == "UniqueConstraint":
            lines.append(f"        sa.UniqueConstraint({', '.join(src(a) for a in e.args)}, name={src(kw(e, 'name'))}),")
        elif name == "Index":
            idx.append(f'    op.create_index({src(e.args[0])}, "{t}", [{", ".join(src(a) for a in e.args[1:])}])')
    lines.append("    )")
    return lines, idx


def _header(revision: str, down: str | None, doc: str) -> list[str]:
    return [f'"""{doc}', "", f"Revision ID: {revision}", f"Revises: {down or ''}", '"""', "", "import sqlalchemy as sa", "from alembic import op", "from sqlalchemy.dialects import postgresql", "",
            f'revision = "{revision}"', f'down_revision = "{down}"' if down else "down_revision = None", "branch_labels = None", "depends_on = None", "", "", "def upgrade() -> None:"]  # fmt: skip


def emit() -> str:
    """Migration 0001: the initial 37 tables, without the columns added later."""
    tables = parse_models()
    specs = column_specs(tables)
    lines = _header("0001", None, "Initial schema (generated from app/db/models by scripts/generate_initial_migration.py).")
    idx_lines: list[str] = []
    ordered = [t for t in order(tables, specs) if t in INITIAL_TABLES]
    for t in ordered:
        blk, idx = _table_block(t, specs, tables, set(LATER_COLUMNS.get(t, [])), LATER_COLUMN_TYPES.get(t))
        lines += blk
        idx_lines += idx
    lines += idx_lines + ["", "", "def downgrade() -> None:"]
    lines += [f'    op.drop_table("{t}")' for t in reversed(ordered)]
    return "\n".join(lines) + "\n"


def emit_second() -> str:
    """Migration 0004: new tables + the columns added after 0001."""
    tables = parse_models()
    specs = column_specs(tables)
    lines = _header("0004", "0003", "Multilingual/voice fields, mobile sessions, job lifecycle timestamps, workflow rules, emergency contacts, government submissions, push devices.")
    ordered = [t for t in order(tables, specs) if t in SECOND_TABLES]
    idx_lines: list[str] = []
    for t in ordered:
        blk, idx = _table_block(t, specs, tables, set())
        lines += blk
        idx_lines += idx
    for t, cols in LATER_COLUMNS.items():
        for c in specs[t]:
            if c["name"] in cols:
                args = [f'"{c["name"]}"', c["type"], f"nullable={c['nullable']}"]
                if c["server_default"]:
                    args.append(f"server_default={c['server_default']}")
                lines.append(f'    op.add_column("{t}", sa.Column({", ".join(args)}))')
    lines += idx_lines + ["", "", "def downgrade() -> None:"]
    for t, cols in reversed(list(LATER_COLUMNS.items())):
        lines += [f'    op.drop_column("{t}", "{c}")' for c in reversed(cols)]
    lines += [f'    op.drop_table("{t}")' for t in reversed(ordered)]
    return "\n".join(lines) + "\n"


def emit_third() -> str:
    """Migration 0005: Golden Record links, integration exceptions, cross-portal tracking, classification corrections."""
    tables = parse_models()
    specs = column_specs(tables)
    lines = _header("0005", "0004", "Interoperability layer support (Golden Record links, integration exception queue, cross-portal tracking) and classification-correction capture for the learning loop.")
    ordered = [t for t in order(tables, specs) if t in THIRD_TABLES]
    idx_lines: list[str] = []
    for t in ordered:
        blk, idx = _table_block(t, specs, tables, set())
        lines += blk
        idx_lines += idx
    lines += idx_lines + ["", "", "def downgrade() -> None:"]
    lines += [f'    op.drop_table("{t}")' for t in reversed(ordered)]
    return "\n".join(lines) + "\n"


def emit_fourth() -> str:
    """Migration 0006: full-text legal judgment corpus (public case law, not citizen documents)."""
    tables = parse_models()
    specs = column_specs(tables)
    lines = _header("0006", "0005", "Full-text legal judgment corpus: legal_judgments + legal_judgment_chunks (public case law).\nThe pgvector column/index live in migrations 0007/0008, same split as 0002/0003 for document_chunks.")
    ordered = [t for t in order(tables, specs) if t not in INITIAL_TABLES and t not in SECOND_TABLES and t not in THIRD_TABLES]
    idx_lines: list[str] = []
    for t in ordered:
        blk, idx = _table_block(t, specs, tables, set())
        lines += blk
        idx_lines += idx
    lines += idx_lines + ["", "", "def downgrade() -> None:"]
    lines += [f'    op.drop_table("{t}")' for t in reversed(ordered)]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    targets = {ROOT / "alembic/versions/0001_initial_schema.py": emit(), ROOT / "alembic/versions" / SECOND_TARGET: emit_second(), ROOT / "alembic/versions" / THIRD_TARGET: emit_third(),
               ROOT / "alembic/versions" / FOURTH_TARGET: emit_fourth()}  # fmt: skip
    if "--check" in sys.argv:
        raise SystemExit(0 if all(p.exists() and p.read_text(encoding="utf-8") == t for p, t in targets.items()) else 1)
    for p, t in targets.items():
        p.write_text(t)
        print(f"wrote {p.name} ({t.count('op.create_table')} tables, {t.count('op.add_column')} added columns)")
