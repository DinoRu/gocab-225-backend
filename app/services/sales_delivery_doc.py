from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.core.units import format_qty_unit

COMPANY_NAME = "SEP CI"
COMPANY_INFO = [
    "Abidjan, Côte d'Ivoire",
    # "N° Contribuable : XXXXXXXXX",
    "Tél : +225 07 00 51 51 00",
]


def _fcfa(v) -> str:
    return f"{int(Decimal(str(v))):,}".replace(",", " ") + " FCFA"


def build_delivery_pdf(dn: dict) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=20, textColor=colors.HexColor("#5b48c8"))
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6b7280"))

    story = []
    story.append(Paragraph("BON DE LIVRAISON", title_style))
    story.append(Paragraph(COMPANY_NAME, styles["Heading2"]))
    for line in COMPANY_INFO:
        story.append(Paragraph(line, small))
    story.append(Spacer(1, 6 * mm))

    header = [
        [Paragraph(f"<b>N° BL :</b> {dn['delivery_number']}", styles["Normal"]),
         Paragraph(f"<b>Date :</b> {dn['delivery_date']}", styles["Normal"])],
        [Paragraph(f"<b>Client :</b> {dn['client_name']}", styles["Normal"]),
         Paragraph(f"<b>Vente liée :</b> {dn['sale_number']}", styles["Normal"])],
    ]
    ht = Table(header, colWidths=[95 * mm, 75 * mm])
    ht.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(ht)
    story.append(Spacer(1, 6 * mm))

    # Uniquement les lignes livrées — pas de "reste"
    data = [["Désignation", "Qté livrée", "Prix unitaire", "Total"]]
    for it in dn["items"]:
        data.append([
            it["designation"],
            str(it["quantity"]),  # ← "10 pièce", "5 litre"
            _fcfa(it["sale_price"]),
            _fcfa(it["line_total"]),
        ])
    data.append(["", "", "TOTAL", _fcfa(dn["total"])])

    table = Table(data, colWidths=[80 * mm, 30 * mm, 32 * mm, 33 * mm])
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

    if dn.get("notes"):
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(f"<b>Notes :</b> {dn['notes']}", small))

    # Zone de signature (document de réception)
    story.append(Spacer(1, 16 * mm))
    sign = Table(
        [[Paragraph("Livré par : SEP CI", small), Paragraph("Reçu par (nom & signature) :", small)]],
        colWidths=[85 * mm, 85 * mm],
    )
    sign.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.HexColor("#9ca3af")), ("TOPPADDING", (0, 0), (-1, -1), 14)]))
    story.append(sign)

    doc.build(story)
    buffer.seek(0)
    return buffer