"""Import every model so ``Base.metadata`` is complete (Alembic autogenerate and repositories rely on it)."""

from app.db.models import complaints, content, identity, ops, reference  # noqa: F401
