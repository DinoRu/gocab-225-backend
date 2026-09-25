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


def build_ledger_pdf(ledger: dict) -> BytesIO:
    """ledger = la sortie de client_ledger (client_name, total_sold, total_paid, balance, entries)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=19, textColor=colors.HexColor("#5b48c8"))
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6b7280"))

    story = []
    story.append(Paragraph("RELEVÉ DE COMPTE", title_style))
    story.append(Paragraph(COMPANY_NAME, styles["Heading2"]))
    for line in COMPANY_INFO:
        story.append(Paragraph(line, small))
    story.append(Spacer(1, 6 * mm))

    # En-tête client + récap
    story.append(Paragraph(f"<b>Client :</b> {ledger['client_name']}", styles["Normal"]))
    story.append(Spacer(1, 3 * mm))

    recap = [
        ["Total vendu (TTC)", _fcfa(ledger["total_sold"])],
        ["Total payé", _fcfa(ledger["total_paid"])],
        ["Solde dû", _fcfa(ledger["balance"])],
    ]
    recap_table = Table(recap, colWidths=[60 * mm, 50 * mm])
    recap_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 2), (1, 2), colors.HexColor("#b91c1c")),
        ("LINEABOVE", (0, 2), (-1, 2), 0.5, colors.HexColor("#5b48c8")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(recap_table)
    story.append(Spacer(1, 8 * mm))

    # Relevé chronologique
    story.append(Paragraph("<b>Relevé chronologique</b>", styles["Normal"]))
    story.append(Spacer(1, 2 * mm))

    data = [["Date", "Opération", "Débit", "Crédit", "Solde"]]
    for e in ledger["entries"]:
        kind = "Vente" if e["kind"] == "sale" else "Versement"
        data.append([
            str(e["date"]),
            f"{e['ref']} — {kind}",
            _fcfa(e["debit"]) if e["debit"] is not None else "",
            _fcfa(e["credit"]) if e["credit"] is not None else "",
            _fcfa(e["running_balance"]),
        ])

    table = Table(data, colWidths=[24 * mm, 62 * mm, 30 * mm, 30 * mm, 30 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5b48c8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e4e9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Débit = montant vendu (TTC) · Crédit = versement reçu · Solde = ce que le client doit.",
        small,
    ))
    story.append(Spacer(1, 2 * mm))
    from datetime import date as _date
    story.append(Paragraph(f"Relevé édité le {_date.today().strftime('%d/%m/%Y')}.", small))

    doc.build(story)
    buffer.seek(0)
    return buffer