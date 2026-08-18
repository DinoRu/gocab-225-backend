# app/core/tax.py
from decimal import Decimal, ROUND_HALF_UP

VAT_RATE = Decimal("0.18")   # 18% — TVA Côte d'Ivoire, appliquée à toutes les ventes


def vat_amount(ht: Decimal) -> Decimal:
    """TVA sur un montant HT, arrondie au FCFA (pas de centimes)."""
    return (Decimal(ht) * VAT_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def ttc_amount(ht: Decimal) -> Decimal:
    """Montant TTC = HT + TVA."""
    return Decimal(ht) + vat_amount(Decimal(ht))