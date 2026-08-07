from sqlalchemy.exc import IntegrityError


def constraint_name(exc: IntegrityError) -> str | None:
    """Nom de la contrainte violée (asyncpg), ou None si indéterminé."""
    orig = getattr(exc, "orig", None)
    cause = getattr(orig, "__cause__", None) or orig
    return getattr(cause, "constraint_name", None)


