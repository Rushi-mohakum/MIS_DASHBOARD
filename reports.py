"""Downloadable PDF report builder."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _money(value: float) -> str:
    return f"INR {float(value):,.2f}"


def build_pdf_report(data: dict, quality: dict, filename: str, insights: str | None = None) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="MIS Intelligence Studio Report",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontSize=22, leading=26, textColor=colors.HexColor("#3B0764"), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=14, leading=18, textColor=colors.HexColor("#6D28D9"), spaceBefore=8, spaceAfter=8))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8.5, leading=12))

    purple = colors.HexColor("#6D28D9")
    dark = colors.HexColor("#160B36")
    pink = colors.HexColor("#DB2777")
    pale = colors.HexColor("#F5F3FF")
    border = colors.HexColor("#D8B4FE")

    def table(data_rows, widths=None, header=True):
        t = Table(data_rows, colWidths=widths, repeatRows=1 if header else 0)
        rules = [
            ("GRID", (0, 0), (-1, -1), 0.5, border),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ]
        if header:
            rules += [
                ("BACKGROUND", (0, 0), (-1, 0), dark),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
            if len(data_rows) > 1:
                rules.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, pale]))
        t.setStyle(TableStyle(rules))
        return t

    story = [
        Paragraph("MIS Intelligence Studio", styles["ReportTitle"]),
        Paragraph("Business MIS + AI Analytics Report", styles["Heading2"]),
        Paragraph(f"Source: {filename} | Generated: {datetime.now().strftime('%d %B %Y, %I:%M %p')}", styles["Small"]),
        Spacer(1, 10),
    ]

    kpi = data["kpi"]
    kpi_rows = [
        ["Net Sales", "Gross Profit", "EBITDA", "Net Profit", "Inventory Value", "Units Sold"],
        [
            _money(kpi["net_sales"]),
            _money(kpi["gross_profit"]),
            _money(kpi["ebitda"]),
            _money(kpi["net_profit"]),
            _money(kpi["inventory_value"]) if kpi["has_stock"] else "Not available",
            f"{kpi['units_sold']:,.0f}",
        ],
    ]
    story += [table(kpi_rows, widths=[42 * mm] * 6), Spacer(1, 12)]

    story.append(Paragraph("Data Quality", styles["Section"]))
    quality_rows = [
        ["Rows", "Columns", "Missing Values", "Duplicate Rows", "Numeric Columns", "Quality Score"],
        [
            f"{quality['rows']:,}",
            f"{quality['columns']:,}",
            f"{quality['missing']:,} ({quality['missing_pct']}%)",
            f"{quality['duplicates']:,} ({quality['duplicate_pct']}%)",
            str(quality["numeric"]),
            f"{quality['score']}/100",
        ],
    ]
    story += [table(quality_rows, widths=[42 * mm] * 6), Spacer(1, 10)]

    story.append(Paragraph("Top Products", styles["Section"]))
    product_rows = [["Product", "Category", "Units Sold", "Net Sales", "Gross Profit", "Net Profit", "NP Margin"]]
    for p in data.get("top_products", [])[:10]:
        product_rows.append([
            str(p["product"]), str(p["category"]), f"{p['units_sold']:,.0f}", _money(p["net_sales"]),
            _money(p["gross_profit"]), _money(p["net_profit"]), f"{p['np_margin']}%",
        ])
    if len(product_rows) == 1:
        product_rows.append(["No product data", "", "", "", "", "", ""])
    story += [table(product_rows, widths=[48 * mm, 38 * mm, 25 * mm, 34 * mm, 34 * mm, 34 * mm, 24 * mm]), PageBreak()]

    story.append(Paragraph("Category Performance", styles["Section"]))
    category_rows = [["Category", "Net Sales", "Gross Profit", "GP Margin", "Share of Sales", "Units Sold"]]
    for c in data.get("category_performance", [])[:12]:
        category_rows.append([
            str(c["category"]), _money(c["net_sales"]), _money(c["gross_profit"]),
            f"{c['gp_margin']}%", f"{c['share_pct']}%", f"{c['units_sold']:,.0f}",
        ])
    if len(category_rows) == 1:
        category_rows.append(["No category data", "", "", "", "", ""])
    story += [table(category_rows, widths=[55 * mm, 42 * mm, 42 * mm, 30 * mm, 34 * mm, 30 * mm]), Spacer(1, 12)]

    if insights:
        story.append(Paragraph("Management Insights", styles["Section"]))
        for line in insights.splitlines():
            clean = line.strip().lstrip("#").strip()
            if not clean:
                continue
            if line.strip().startswith("####"):
                story.append(Paragraph(clean, styles["Heading3"]))
            elif clean.startswith("-"):
                story.append(Paragraph("• " + clean[1:].strip(), styles["Small"]))
            else:
                story.append(Paragraph(clean, styles["Small"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Generated by MIS Intelligence Studio. Figures depend on the uploaded source data and mapped columns.", styles["Small"]))
    doc.build(story)
    buffer.seek(0)
    return buffer
