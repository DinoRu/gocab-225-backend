def escape_like(term: str) -> str:
    """Neutralise les wildcards LIKE pour qu'un % ou _ tapé soit littéral."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")