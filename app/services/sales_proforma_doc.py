from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from app.core.tax import vat_amount, ttc_amount
# from app.core.units import format_qty_unit


def _fcfa(v) -> str:
    return f"{int(Decimal(str(v))):,}".replace(",", " ") + " FCFA"


def build_proforma_pdf(pf: dict) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#5b48c8"))
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6b7280"))

    story = []
    story.append(Paragraph("FACTURE PROFORMA", title_style))
    story.append(Paragraph("SEP CI", small))
    story.append(Paragraph("02 BP 1323 Abidjan 02", small))
    story.append(Paragraph("Tél : +225 07 00 51 51 00", small))
    story.append(Spacer(1, 8 * mm))

    # En-tête : n°, date, client
    header = [
        [Paragraph(f"<b>N° :</b> {pf['proforma_number']}", styles["Normal"]),
         Paragraph(f"<b>Date :</b> {pf['proforma_date']}", styles["Normal"])],
        [Paragraph(f"<b>Client :</b> {pf['client_name']}", styles["Normal"]), ""],
    ]
    ht = Table(header, colWidths=[90 * mm, 80 * mm])
    ht.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(ht)
    story.append(Spacer(1, 6 * mm))

    # Lignes
    data = [["Désignation", "Qté", "Prix unitaire", "Total"]]
    for it in pf["items"]:
        qty_label = str(it["quantity"])
        data.append([
            it["designation"],
            qty_label,                          # ← "10 pièce", "5 litre"…
            _fcfa(it["sale_price"]),
            _fcfa(it["line_total"]),
        ])
    data.append(["", "", "TOTAL", _fcfa(pf["total"])])

    table = Table(data, colWidths=[85 * mm, 20 * mm, 35 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5b48c8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -2), 0.4, colors.HexColor("#e2e4e9")),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#5b48c8")),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    
    ht = Decimal(str(pf["total"]))       # total des lignes = HT
    tva = vat_amount(ht)
    ttc = ht + tva

    totals_data = [
        ["", "Total HT", _fcfa(ht)],
        ["", "TVA (18%)", _fcfa(tva)],
        ["", "Total TTC", _fcfa(ttc)],
    ]
    totals_table = Table(totals_data, colWidths=[105 * mm, 35 * mm, 35 * mm])
    totals_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (1, 2), (-1, 2), "Helvetica-Bold"),   # TTC en gras
        ("LINEABOVE", (1, 2), (-1, 2), 1, colors.HexColor("#5b48c8")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(totals_table)

    if pf.get("notes"):
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(f"<b>Notes :</b> {pf['notes']}", small))

    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("Ce document est une facture proforma, sans valeur comptable.", small))

    doc.build(story)
    buffer.seek(0)
    return buffer