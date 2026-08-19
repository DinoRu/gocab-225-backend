UNIT_PLURALS = {
    "pièce": "pièces",
    "jeu": "jeux",
    "paire": "paires",
    "litre": "litres",
    "kg": "kg",
    "mètre": "mètres",
    "boîte": "boîtes",
    "lot": "lots",
    "rouleau": "rouleaux",
    "sachet": "sachets",
}


def format_unit(quantity: int, unit: str) -> str:
    if quantity >= 2:
        return UNIT_PLURALS.get(unit, unit)
    return unit


def format_qty_unit(quantity: int, unit: str) -> str:
    return f"{quantity} {format_unit(quantity, unit)}"