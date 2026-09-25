"""Import every model so ``Base.metadata`` is complete (Alembic autogenerate and repositories rely on it)."""

from app.db.models import (  # noqa: F401
    complaints,
    content,
    identity,
    interop_platform,
    ops,
    reference,
)
