import base64
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

COMPANY_NAME = "SEP CI"
COMPANY_INFO = [
    "Abidjan, Côte d'Ivoire",
    "N° Contribuable : 2301098Z",
    "Tél : +225 07 00 51 51 00",
]


def _fcfa(v) -> str:
    return f"{int(Decimal(str(v))):,}".replace(",", " ") + " FCFA"


def build_invoice_pdf(inv: dict) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=20, textColor=colors.HexColor(("#1e3a8a")))
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6b7280"))

    company_style = ParagraphStyle(
        "company",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#1e3a8a"),
    )
    story = []
    story.append(Paragraph("FACTURE", title_style))
    story.append(Paragraph(COMPANY_NAME, company_style))
    for line in COMPANY_INFO:
        story.append(Paragraph(line, small))
    story.append(Spacer(1, 6 * mm))

    header = [
        [Paragraph(f"<b>N° Facture :</b> {inv['invoice_number']}", styles["Normal"]),
         Paragraph(f"<b>Date :</b> {inv['invoice_date']}", styles["Normal"])],
        [Paragraph(f"<b>Client :</b> {inv['client_name']}", styles["Normal"]), ""],
    ]
    ht_tbl = Table(header, colWidths=[95 * mm, 75 * mm])
    ht_tbl.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(ht_tbl)
    story.append(Spacer(1, 6 * mm))

    data = [["Désignation", "Qté", "Prix unitaire", "Total"]]
    for it in inv["items"]:
        data.append([it["designation"], str(it["quantity"]), _fcfa(it["sale_price"]), _fcfa(it["line_total"])])

    table = Table(data, colWidths=[85 * mm, 20 * mm, 35 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a ")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e4e9")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eff4ff")]),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    # Totaux : avec TVA ou non selon le flag figé
    if inv["vat_applicable"]:
        totals = [
            ["", "Total HT", _fcfa(inv["total_ht"])],
            ["", "TVA (18%)", _fcfa(inv["vat_amount"])],
            ["", "Total TTC", _fcfa(inv["total_ttc"])],
        ]
    else:
        totals = [["", "TOTAL", _fcfa(inv["total_ht"])]]
    tt = Table(totals, colWidths=[95 * mm, 45 * mm, 35 * mm])
    tt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (1, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (1, -1), (-1, -1), 1, colors.HexColor("#1e3a8a")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eff4ff")]),
    ]))
    story.append(tt)

    doc.build(story)
    buffer.seek(0)
    return buffer