"""Import every model so ``Base.metadata`` is complete (Alembic autogenerate and repositories rely on it)."""

from app.db.models import complaints, content, identity, interop_platform, ops, reference  # noqa: F401
