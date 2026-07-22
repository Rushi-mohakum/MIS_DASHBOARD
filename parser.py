"""
parser.py — turns an uploaded file (xlsx/xls/csv/pdf/docx) into a normalized
DataFrame, then computes every number the dashboard needs.

Design goal: the person uploading data shouldn't have to match an exact
schema. Common column-name variants are auto-mapped. Missing columns get
sane defaults (and a warning) instead of crashing.
"""
import pandas as pd

# canonical_column -> list of accepted header spellings (normalized: lowercase, spaces/dashes -> underscore)
COLUMN_ALIASES = {
    "date":          ["date", "entry_date", "month", "order_date", "transaction_date", "period"],
    "product":       ["product", "item", "item_name", "sku", "product_name"],
    "category":      ["category", "product_category", "type", "segment", "department"],
    "units_sold":    ["units_sold", "qty", "quantity", "units", "qty_sold", "sold_qty"],
    "unit_price":    ["unit_price", "price", "rate", "selling_price", "mrp"],
    "net_sales":     ["net_sales", "sales", "revenue", "total_sales", "amount", "gross_sales"],
    "unit_cost":     ["unit_cost", "cost", "cost_price", "cogs_per_unit", "purchase_price"],
    "cogs":          ["cogs", "cost_of_goods_sold", "total_cost"],
    "opex":          ["opex", "operating_expense", "operating_expenses", "expenses"],
    "stock_qty":     ["stock_qty", "stock", "inventory", "current_stock", "closing_stock", "on_hand", "stock_on_hand"],
    "reorder_level": ["reorder_level", "reorder_point", "min_stock", "safety_stock", "reorder_qty"],
}


def _norm(s):
    return str(s).strip().lower().replace(" ", "_").replace("-", "_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    reverse = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            reverse[_norm(a)] = canonical
    rename_map = {c: reverse[_norm(c)] for c in df.columns if _norm(c) in reverse}
    df = df.rename(columns=rename_map)
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def extract_pdf_table(path):
    import pdfplumber
    best = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                if not table or len(table) < 2:
                    continue
                if best is None or len(table) > len(best):
                    best = table
    if not best:
        return pd.DataFrame()
    header, *rows = best
    header = [h if h else f"col_{i}" for i, h in enumerate(header)]
    return pd.DataFrame(rows, columns=header)


def extract_docx_table(path):
    from docx import Document
    doc = Document(path)
    best = None
    for table in doc.tables:
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        if best is None or len(rows) > len(best):
            best = rows
    if not best:
        return pd.DataFrame()
    header, *rows = best
    return pd.DataFrame(rows, columns=header)


def load_dataframe(path: str, ext: str):
    """Returns (df, warnings). df always has the full canonical schema, numeric-coerced."""
    warnings = []

    if ext in ("xlsx", "xls"):
        raw = pd.read_excel(path)
    elif ext == "csv":
        raw = pd.read_csv(path)
    elif ext == "pdf":
        raw = extract_pdf_table(path)
        if raw.empty:
            warnings.append("No table detected in the PDF. PDFs work best when they contain a real data table (not a scanned image).")
    elif ext == "docx":
        raw = extract_docx_table(path)
        if raw.empty:
            warnings.append("No table detected in the Word document. Make sure your data is in an actual Word table.")
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    if raw is None or raw.empty:
        return None, warnings

    df = normalize_columns(raw)

    if "product" not in df.columns:
        df["product"] = [f"Item {i+1}" for i in range(len(df))]
        warnings.append("No 'product' column found — using generic item labels.")
    if "category" not in df.columns:
        df["category"] = "Uncategorized"
        warnings.append("No 'category' column found — grouping everything as 'Uncategorized'.")
    if "units_sold" not in df.columns:
        df["units_sold"] = 0
        warnings.append("No units/quantity column found — Units Sold will show as 0.")
    if "net_sales" not in df.columns:
        if "unit_price" in df.columns:
            df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce").fillna(0)
            df["net_sales"] = df["units_sold"] * pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
        else:
            df["net_sales"] = 0
            warnings.append("No sales/revenue data found — add a 'net_sales' or 'unit_price' column for real figures.")
    if "cogs" not in df.columns:
        if "unit_cost" in df.columns:
            df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce").fillna(0)
            df["cogs"] = df["units_sold"] * pd.to_numeric(df["unit_cost"], errors="coerce").fillna(0)
        else:
            df["cogs"] = 0
            warnings.append("No cost data found — add a 'cogs' or 'unit_cost' column to see real profit figures.")
    if "opex" not in df.columns:
        df["opex"] = 0
    if "stock_qty" not in df.columns:
        df["stock_qty"] = None
        warnings.append("No stock/inventory column found — inventory metrics will be blank.")
    if "reorder_level" not in df.columns:
        df["reorder_level"] = None
    if "date" not in df.columns:
        df["date"] = None

    for col in ["units_sold", "net_sales", "cogs", "opex"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in ["stock_qty", "reorder_level"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df, warnings


def compute_dashboard_data(df: pd.DataFrame, tax_rate: float = 0.25) -> dict:
    net_sales = float(df["net_sales"].sum())
    cogs = float(df["cogs"].sum())
    gross_profit = net_sales - cogs
    opex = float(df["opex"].sum())
    ebitda = gross_profit - opex
    ebit = ebitda        # no depreciation data available from a generic upload
    pbt = ebit            # no interest/other-income data available
    net_profit = pbt * (1 - tax_rate)
    units_sold = float(df["units_sold"].sum())

    gp_margin = round(gross_profit / net_sales * 100, 1) if net_sales else 0
    ebitda_margin = round(ebitda / net_sales * 100, 1) if net_sales else 0
    np_margin = round(net_profit / net_sales * 100, 1) if net_sales else 0

    # ---- Per-product rollup ----
    grouped = df.groupby("product", dropna=False).agg(
        category=("category", "first"),
        units_sold=("units_sold", "sum"),
        net_sales=("net_sales", "sum"),
        cogs=("cogs", "sum"),
        opex=("opex", "sum"),
        stock_qty=("stock_qty", "max"),
        reorder_level=("reorder_level", "max"),
    ).reset_index()
    grouped["gross_profit"] = grouped["net_sales"] - grouped["cogs"]
    grouped["net_profit"] = (grouped["gross_profit"] - grouped["opex"]) * (1 - tax_rate)
    grouped["np_margin"] = grouped.apply(
        lambda r: round(r["net_profit"] / r["net_sales"] * 100, 1) if r["net_sales"] else 0, axis=1
    )
    grouped["unit_cost_est"] = grouped.apply(
        lambda r: (r["cogs"] / r["units_sold"]) if r["units_sold"] else 0, axis=1
    )

    def _clean_records(d):
        out = []
        for rec in d:
            out.append({k: (v.item() if hasattr(v, "item") else v) for k, v in rec.items()})
        return out

    top_products = _clean_records(
        grouped.sort_values("net_sales", ascending=False).head(10).to_dict("records")
    )

    # ---- Inventory ----
    has_stock = grouped["stock_qty"].notna().any()
    stock_qty_total = float(grouped["stock_qty"].fillna(0).sum())
    inventory_value = float((grouped["stock_qty"].fillna(0) * grouped["unit_cost_est"]).sum())
    denom = units_sold + stock_qty_total
    sell_through_pct = round(units_sold / denom * 100, 1) if denom else 0

    if has_stock:
        alerts_df = grouped[grouped["stock_qty"].notna() & (grouped["stock_qty"] <= grouped["reorder_level"].fillna(0))]
        stock_alerts = _clean_records(alerts_df.to_dict("records"))
    else:
        stock_alerts = []

    # ---- Category mix ----
    by_cat = df.groupby("category", dropna=False)["net_sales"].sum().sort_values(ascending=False)
    mix_labels = [str(x) for x in by_cat.index[:6]]
    mix_values = [round(float(v), 2) for v in by_cat.values[:6]]
    if len(by_cat) > 6:
        other = round(float(by_cat.values[6:].sum()), 2)
        if other:
            mix_labels.append("Other")
            mix_values.append(other)

    # ---- Monthly trend ----
    trend = {"labels": [], "net_sales": [], "gross_profit": [], "ebitda": [], "net_profit": []}
    if df["date"].notna().any():
        d = df.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date"])
        if not d.empty:
            d["month"] = d["date"].dt.to_period("M").astype(str)
            m = d.groupby("month").agg(
                net_sales=("net_sales", "sum"),
                cogs=("cogs", "sum"),
                opex=("opex", "sum"),
            ).sort_index()
            m["gross_profit"] = m["net_sales"] - m["cogs"]
            m["ebitda"] = m["gross_profit"] - m["opex"]
            m["net_profit"] = m["ebitda"] * (1 - tax_rate)
            trend = {
                "labels": [str(x) for x in m.index],
                "net_sales": [round(float(v), 2) for v in m["net_sales"]],
                "gross_profit": [round(float(v), 2) for v in m["gross_profit"]],
                "ebitda": [round(float(v), 2) for v in m["ebitda"]],
                "net_profit": [round(float(v), 2) for v in m["net_profit"]],
            }

    # ---- Category performance (for the advanced breakdown table) ----
    cat_perf = df.groupby("category", dropna=False).agg(
        net_sales=("net_sales", "sum"),
        cogs=("cogs", "sum"),
        units_sold=("units_sold", "sum"),
    ).reset_index()
    cat_perf["gross_profit"] = cat_perf["net_sales"] - cat_perf["cogs"]
    cat_perf["gp_margin"] = cat_perf.apply(
        lambda r: round(r["gross_profit"] / r["net_sales"] * 100, 1) if r["net_sales"] else 0, axis=1
    )
    cat_perf["share_pct"] = cat_perf.apply(
        lambda r: round(r["net_sales"] / net_sales * 100, 1) if net_sales else 0, axis=1
    )
    cat_perf = _clean_records(cat_perf.sort_values("net_sales", ascending=False).to_dict("records"))

    # ---- Month-over-month growth (needs at least 2 months of trend data) ----
    momentum = {"net_sales_growth_pct": None, "units_growth_pct": None, "has_momentum": False}
    if len(trend["labels"]) >= 2:
        prev_sales, last_sales = trend["net_sales"][-2], trend["net_sales"][-1]
        if prev_sales:
            momentum["net_sales_growth_pct"] = round((last_sales - prev_sales) / prev_sales * 100, 1)
        momentum["has_momentum"] = True
        momentum["last_month"] = trend["labels"][-1]
        momentum["prev_month"] = trend["labels"][-2]

    return {
        "kpi": {
            "net_sales": net_sales,
            "gross_profit": gross_profit,
            "gp_margin": gp_margin,
            "ebitda": ebitda,
            "ebitda_margin": ebitda_margin,
            "net_profit": net_profit,
            "np_margin": np_margin,
            "units_sold": units_sold,
            "inventory_value": inventory_value,
            "sell_through_pct": sell_through_pct,
            "stock_alerts_count": len(stock_alerts),
            "has_stock": has_stock,
            "sku_count": len(grouped),
        },
        "pnl": {
            "gross_sales": net_sales,   # no returns/discounts data in a generic upload
            "net_sales": net_sales,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "opex": opex,
            "ebitda": ebitda,
            "ebit": ebit,
            "pbt": pbt,
            "net_profit": net_profit,
        },
        "trend": trend,
        "momentum": momentum,
        "mix_labels": mix_labels,
        "mix_values": mix_values,
        "top_products": top_products,
        "category_performance": cat_perf,
        "stock_alerts": stock_alerts,
    }


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def build_excel_report(df: pd.DataFrame, data: dict, tax_rate: float) -> "BytesIO":
    from io import BytesIO
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    HEADER_FILL = PatternFill(start_color="1F4E5F", end_color="1F4E5F", fill_type="solid")
    HEADER_FONT = Font(color="FFFFFF", bold=True)
    TITLE_FONT = Font(size=16, bold=True, color="1F4E5F")
    SUBTITLE_FONT = Font(size=10, italic=True, color="666666")
    LABEL_FONT = Font(bold=True)
    THIN_BORDER = Border(*(Side(style="thin", color="DDDDDD"),) * 4)
    CENTER = Alignment(horizontal="center", vertical="center")

    def style_header(ws, row, ncols):
        for col in range(1, ncols + 1):
            cell = ws.cell(row=row, column=col)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = CENTER
            cell.border = THIN_BORDER

    def autosize(ws):
        for col in ws.columns:
            length = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(length + 3, 40)

    def write_table(ws, start_row, headers, rows):
        for i, h in enumerate(headers, start=1):
            ws.cell(row=start_row, column=i, value=h)
        style_header(ws, start_row, len(headers))
        for r_idx, row in enumerate(rows, start=start_row + 1):
            for c_idx, val in enumerate(row, start=1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.border = THIN_BORDER
        return start_row + len(rows) + 1

    wb = Workbook()
    kpi, pnl = data["kpi"], data["pnl"]

    # ---- Summary sheet ----
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "MIS Dashboard — Summary"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  Assumed tax rate {round(tax_rate*100)}%"
    ws["A2"].font = SUBTITLE_FONT
    ws.merge_cells("A1:D1")
    ws.merge_cells("A2:D2")

    rows = [
        ("Net Sales", round(kpi["net_sales"], 2)),
        ("Gross Profit", round(kpi["gross_profit"], 2)),
        ("GP Margin %", kpi["gp_margin"]),
        ("EBITDA", round(kpi["ebitda"], 2)),
        ("EBITDA Margin %", kpi["ebitda_margin"]),
        ("Net Profit", round(kpi["net_profit"], 2)),
        ("NP Margin %", kpi["np_margin"]),
        ("Units Sold", round(kpi["units_sold"], 2)),
        ("Inventory Value", round(kpi["inventory_value"], 2)),
        ("Sell-Through Rate %", kpi["sell_through_pct"]),
        ("Stock Alerts", kpi["stock_alerts_count"]),
        ("Products Tracked", kpi["sku_count"]),
    ]
    row = 4
    ws.cell(row=row, column=1, value="Metric").font = LABEL_FONT
    ws.cell(row=row, column=2, value="Value").font = LABEL_FONT
    style_header(ws, row, 2)
    for i, (label, val) in enumerate(rows, start=row + 1):
        ws.cell(row=i, column=1, value=label).border = THIN_BORDER
        ws.cell(row=i, column=2, value=val).border = THIN_BORDER
    autosize(ws)

    # ---- P&L sheet ----
    ws2 = wb.create_sheet("P&L Snapshot")
    ws2["A1"] = "Profit & Loss Snapshot"
    ws2["A1"].font = TITLE_FONT
    ws2["A2"] = "Gross Sales assumed = Net Sales; EBIT/PBT assumed = EBITDA (generic upload has no returns/depreciation/interest data)."
    ws2["A2"].font = SUBTITLE_FONT
    pnl_rows = [
        ("Gross Sales", round(pnl["gross_sales"], 2)),
        ("Net Sales", round(pnl["net_sales"], 2)),
        ("COGS", round(pnl["cogs"], 2)),
        ("Gross Profit", round(pnl["gross_profit"], 2)),
        ("OpEx", round(pnl["opex"], 2)),
        ("EBITDA", round(pnl["ebitda"], 2)),
        ("EBIT", round(pnl["ebit"], 2)),
        ("PBT", round(pnl["pbt"], 2)),
        ("Net Profit", round(pnl["net_profit"], 2)),
    ]
    write_table(ws2, 4, ["Line Item", "Amount"], pnl_rows)
    autosize(ws2)

    # ---- Top Products sheet ----
    ws3 = wb.create_sheet("Top Products")
    headers = ["Product", "Category", "Units Sold", "Net Sales", "Gross Profit", "Net Profit", "NP Margin %"]
    prod_rows = [
        [p["product"], p["category"], round(p["units_sold"], 2), round(p["net_sales"], 2),
         round(p["gross_profit"], 2), round(p["net_profit"], 2), p["np_margin"]]
        for p in data["top_products"]
    ]
    if not prod_rows:
        prod_rows = [["No product data", "", "", "", "", "", ""]]
    write_table(ws3, 1, headers, prod_rows)
    autosize(ws3)

    # ---- Category performance sheet ----
    ws4 = wb.create_sheet("Category Performance")
    cat_headers = ["Category", "Net Sales", "Gross Profit", "GP Margin %", "Share of Sales %", "Units Sold"]
    cat_rows = [
        [c["category"], round(c["net_sales"], 2), round(c["gross_profit"], 2), c["gp_margin"], c["share_pct"], round(c["units_sold"], 2)]
        for c in data["category_performance"]
    ]
    if not cat_rows:
        cat_rows = [["No category data", "", "", "", "", ""]]
    write_table(ws4, 1, cat_headers, cat_rows)
    autosize(ws4)

    # ---- Monthly trend sheet ----
    ws5 = wb.create_sheet("Monthly Trend")
    if data["trend"]["labels"]:
        t_headers = ["Month", "Net Sales", "Gross Profit", "EBITDA", "Net Profit"]
        t_rows = list(zip(
            data["trend"]["labels"], data["trend"]["net_sales"],
            data["trend"]["gross_profit"], data["trend"]["ebitda"], data["trend"]["net_profit"],
        ))
        write_table(ws5, 1, t_headers, [list(r) for r in t_rows])
    else:
        ws5["A1"] = "No date column found in the uploaded file — no monthly trend available."
    autosize(ws5)

    # ---- Inventory alerts sheet ----
    ws6 = wb.create_sheet("Inventory Alerts")
    if data["stock_alerts"]:
        a_headers = ["Product", "Category", "Stock Qty", "Reorder Level"]
        a_rows = [[a["product"], a["category"], a["stock_qty"], a.get("reorder_level")] for a in data["stock_alerts"]]
        write_table(ws6, 1, a_headers, a_rows)
    else:
        ws6["A1"] = "No products at or below reorder level."
    autosize(ws6)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# PowerPoint export
# ---------------------------------------------------------------------------

def build_ppt_report(df: pd.DataFrame, data: dict, tax_rate: float) -> "BytesIO":
    """Builds a 7-slide MIS deck (Title, KPI Summary, P&L, Top Products,
    Category Performance, Monthly Trend, Inventory Alerts) from the same
    computed `data` dict used by the dashboard and the Excel export."""
    from io import BytesIO
    from datetime import datetime

    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.enum.shapes import MSO_SHAPE

    # ---- palette (matches the web dashboard) ----
    NAVY = RGBColor(0x1F, 0x4E, 0x5F)
    ORANGE = RGBColor(0xE8, 0xA3, 0x3D)
    TEAL = RGBColor(0x2F, 0xB6, 0xC4)
    GREEN = RGBColor(0x3F, 0xBF, 0x7F)
    RED = RGBColor(0xE0, 0x5A, 0x4E)
    BLUE = RGBColor(0x5B, 0x8D, 0xEF)
    MUTED = RGBColor(0x6B, 0x76, 0x85)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    LIGHT_BG = RGBColor(0xF4, 0xF6, 0xF8)

    SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]

    kpi, pnl = data["kpi"], data["pnl"]

    def add_slide():
        return prs.slides.add_slide(blank)

    def add_rect(slide, x, y, w, h, color, line=False):
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
        shp.fill.solid()
        shp.fill.fore_color.rgb = color
        if line:
            shp.line.color.rgb = color
        else:
            shp.line.fill.background()
        shp.shadow.inherit = False
        return shp

    def add_text(slide, x, y, w, h, text, size=14, bold=False, color=NAVY,
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font="Calibri"):
        tb = slide.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = align
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = font
        return tb

    def slide_header(slide, title, subtitle=None):
        add_rect(slide, 0, 0, SLIDE_W, Inches(1.15), NAVY)
        add_text(slide, Inches(0.5), Inches(0.18), Inches(10), Inches(0.55),
                  title, size=26, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
        if subtitle:
            add_text(slide, Inches(0.5), Inches(0.72), Inches(11), Inches(0.35),
                      subtitle, size=11, color=RGBColor(0xCF, 0xDD, 0xE2), anchor=MSO_ANCHOR.MIDDLE)
        add_text(slide, Inches(10.8), Inches(0.18), Inches(2.3), Inches(0.35),
                  datetime.now().strftime("%d %b %Y"), size=10, color=RGBColor(0xCF, 0xDD, 0xE2),
                  align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)

    def style_table(table, header_color=NAVY, ncols=None):
        ncols = ncols or len(table.columns)
        for c in range(ncols):
            cell = table.cell(0, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_color
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.CENTER
                for r in p.runs:
                    r.font.bold = True
                    r.font.size = Pt(11)
                    r.font.color.rgb = WHITE
        for row_idx in range(1, len(table.rows)):
            for c in range(ncols):
                cell = table.cell(row_idx, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = LIGHT_BG if row_idx % 2 == 0 else WHITE
                for p in cell.text_frame.paragraphs:
                    p.alignment = PP_ALIGN.CENTER if c > 0 else PP_ALIGN.LEFT
                    for r in p.runs:
                        r.font.size = Pt(10.5)
                        r.font.color.rgb = RGBColor(0x22, 0x2A, 0x35)

    def add_table(slide, x, y, w, h, headers, rows):
        n_rows, n_cols = len(rows) + 1, len(headers)
        gtable = slide.shapes.add_table(n_rows, n_cols, x, y, w, h)
        table = gtable.table
        for c, htext in enumerate(headers):
            table.cell(0, c).text = str(htext)
        for r, row in enumerate(rows, start=1):
            for c, val in enumerate(row):
                table.cell(r, c).text = "" if val is None else str(val)
        style_table(table, ncols=n_cols)
        return table

    def money(v):
        try:
            return f"Rs {v:,.0f}"
        except Exception:
            return str(v)

    # ---- Slide 1: Title ----
    s = add_slide()
    add_rect(s, 0, 0, SLIDE_W, SLIDE_H, NAVY)
    add_rect(s, 0, Inches(4.9), SLIDE_W, Inches(0.06), ORANGE)
    add_text(s, Inches(0.9), Inches(2.7), Inches(11.5), Inches(1.1),
              "MIS Dashboard Report", size=44, bold=True, color=WHITE)
    add_text(s, Inches(0.9), Inches(3.65), Inches(11.5), Inches(0.6),
              "Sales - Inventory - Profit & Loss Overview", size=18, color=RGBColor(0xCF, 0xDD, 0xE2))
    add_text(s, Inches(0.9), Inches(5.15), Inches(11.5), Inches(0.4),
              f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')}  |  Assumed tax rate {round(tax_rate*100)}%  |  "
              f"{kpi['sku_count']} products tracked", size=13, color=RGBColor(0xCF, 0xDD, 0xE2))

    # ---- Slide 2: KPI Summary ----
    s = add_slide()
    slide_header(s, "KPI Summary", "Headline numbers computed from the uploaded dataset")
    cards = [
        ("Net Sales", money(kpi["net_sales"]), TEAL),
        ("Gross Profit", money(kpi["gross_profit"]), GREEN),
        ("GP Margin", f"{kpi['gp_margin']}%", GREEN),
        ("EBITDA", money(kpi["ebitda"]), BLUE),
        ("EBITDA Margin", f"{kpi['ebitda_margin']}%", BLUE),
        ("Net Profit", money(kpi["net_profit"]), ORANGE),
        ("NP Margin", f"{kpi['np_margin']}%", ORANGE),
        ("Units Sold", f"{kpi['units_sold']:,.0f}", MUTED),
        ("Inventory Value", money(kpi["inventory_value"]) if kpi["has_stock"] else "-", MUTED),
        ("Sell-Through", f"{kpi['sell_through_pct']}%" if kpi["has_stock"] else "-", TEAL),
        ("Stock Alerts", str(kpi["stock_alerts_count"]), RED if kpi["stock_alerts_count"] else GREEN),
        ("Products Tracked", str(kpi["sku_count"]), NAVY),
    ]
    cols = 4
    margin_x, margin_y = Inches(0.5), Inches(1.5)
    gap = Inches(0.22)
    card_w = Emu(int((SLIDE_W - 2 * margin_x - (cols - 1) * gap) / cols))
    card_h = Inches(1.55)
    for i, (label, value, color) in enumerate(cards):
        r, c = divmod(i, cols)
        x = margin_x + c * (card_w + gap)
        y = margin_y + r * (card_h + gap)
        card = add_rect(s, x, y, card_w, card_h, WHITE)
        card.line.color.rgb = RGBColor(0xE2, 0xE6, 0xEA)
        card.line.width = Pt(1)
        add_rect(s, x, y, Inches(0.08), card_h, color)
        add_text(s, x + Inches(0.25), y + Inches(0.18), card_w - Inches(0.4), Inches(0.4),
                  label.upper(), size=10.5, bold=True, color=MUTED)
        add_text(s, x + Inches(0.25), y + Inches(0.6), card_w - Inches(0.4), Inches(0.75),
                  value, size=22, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)

    # ---- Slide 3: P&L Snapshot ----
    s = add_slide()
    slide_header(s, "Profit & Loss Snapshot",
                 "Gross Sales assumed = Net Sales; EBIT/PBT assumed = EBITDA (no returns/depreciation/interest data)")
    pnl_rows = [
        ("Gross Sales", money(pnl["gross_sales"])),
        ("Net Sales", money(pnl["net_sales"])),
        ("COGS", money(pnl["cogs"])),
        ("Gross Profit", money(pnl["gross_profit"])),
        ("OpEx", money(pnl["opex"])),
        ("EBITDA", money(pnl["ebitda"])),
        ("EBIT", money(pnl["ebit"])),
        ("PBT", money(pnl["pbt"])),
        ("Net Profit", money(pnl["net_profit"])),
    ]
    add_table(s, Inches(1.5), Inches(1.6), Inches(6.3), Inches(4.6), ["Line Item", "Amount"], pnl_rows)

    if pnl["net_sales"]:
        chart_data = CategoryChartData()
        chart_data.categories = ["Net Sales", "Gross Profit", "EBITDA", "Net Profit"]
        chart_data.add_series("Amount", (pnl["net_sales"], pnl["gross_profit"], pnl["ebitda"], pnl["net_profit"]))
        gframe = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(8.1), Inches(1.6),
                                     Inches(4.7), Inches(4.6), chart_data)
        chart = gframe.chart
        chart.has_legend = False
        chart.has_title = True
        chart.chart_title.text_frame.text = "P&L Waterfall (bar view)"
        plot = chart.plots[0]
        plot.has_data_labels = True
        plot.series[0].format.fill.solid()
        plot.series[0].format.fill.fore_color.rgb = TEAL

    # ---- Slide 4: Top Products ----
    s = add_slide()
    slide_header(s, "Top Products", "Ranked by Net Sales")
    headers = ["Product", "Category", "Units", "Net Sales", "Gross Profit", "Net Profit", "NP Margin %"]
    prod_rows = [
        [p["product"], p["category"], f"{p['units_sold']:,.0f}", money(p["net_sales"]),
         money(p["gross_profit"]), money(p["net_profit"]), f"{p['np_margin']}%"]
        for p in data["top_products"][:8]
    ] or [["No product data", "", "", "", "", "", ""]]
    add_table(s, Inches(0.5), Inches(1.4), Inches(12.3), Inches(5.5), headers, prod_rows)

    # ---- Slide 5: Category Performance ----
    s = add_slide()
    slide_header(s, "Category Performance", "Share of sales and margin by category")
    cat_headers = ["Category", "Net Sales", "GP Margin %", "Share %"]
    cat_rows = [
        [c["category"], money(c["net_sales"]), f"{c['gp_margin']}%", f"{c['share_pct']}%"]
        for c in data["category_performance"][:6]
    ] or [["No category data", "", "", ""]]
    add_table(s, Inches(0.5), Inches(1.5), Inches(5.6), Inches(4.6), cat_headers, cat_rows)

    if data["mix_labels"]:
        chart_data = CategoryChartData()
        chart_data.categories = data["mix_labels"]
        chart_data.add_series("Net Sales", data["mix_values"])
        gframe = s.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(6.6), Inches(1.5), Inches(6.2), Inches(4.6), chart_data)
        chart = gframe.chart
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.RIGHT
        chart.legend.include_in_layout = False
        chart.has_title = True
        chart.chart_title.text_frame.text = "Sales Mix by Category"
        plot = chart.plots[0]
        plot.has_data_labels = True
        plot.data_labels.show_percentage = True
        plot.data_labels.show_value = False
        palette = [NAVY, ORANGE, TEAL, GREEN, BLUE, RGBColor(0x9C, 0x6A, 0xDE)]
        for i, point in enumerate(plot.series[0].points):
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = palette[i % len(palette)]

    # ---- Slide 6: Monthly Trend ----
    s = add_slide()
    slide_header(s, "Monthly Trend", "Net Sales, Gross Profit, and Net Profit by month")
    trend = data["trend"]
    if trend["labels"]:
        chart_data = CategoryChartData()
        chart_data.categories = trend["labels"]
        chart_data.add_series("Net Sales", trend["net_sales"])
        chart_data.add_series("Gross Profit", trend["gross_profit"])
        chart_data.add_series("Net Profit", trend["net_profit"])
        gframe = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.6), Inches(1.5),
                                     Inches(12.1), Inches(5.5), chart_data)
        chart = gframe.chart
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        colors = [TEAL, GREEN, ORANGE]
        for i, series in enumerate(chart.plots[0].series):
            series.format.line.color.rgb = colors[i % len(colors)]
            series.format.line.width = Pt(2.25)
    else:
        add_text(s, Inches(0.6), Inches(3.2), Inches(11), Inches(0.6),
                  "No date column found in the uploaded file - no monthly trend available.",
                  size=16, color=MUTED, align=PP_ALIGN.CENTER)

    # ---- Slide 7: Inventory Alerts ----
    s = add_slide()
    stock_alerts = data["stock_alerts"]
    slide_header(s, "Inventory Alerts",
                 f"{len(stock_alerts)} product(s) at or below reorder level" if stock_alerts else "No products at or below reorder level")
    if stock_alerts:
        a_headers = ["Product", "Category", "Stock Qty", "Reorder Level"]
        a_rows = [[a["product"], a["category"], a["stock_qty"], a.get("reorder_level")] for a in stock_alerts[:12]]
        add_table(s, Inches(1.8), Inches(1.6), Inches(9.7), Inches(4.8), a_headers, a_rows)
    else:
        add_rect(s, Inches(3.5), Inches(2.6), Inches(6.3), Inches(2), RGBColor(0xEA, 0xF7, 0xEF))
        add_text(s, Inches(3.8), Inches(3.3), Inches(5.7), Inches(0.7),
                  "All stocked products are above their reorder level.", size=16, bold=True, color=GREEN)

    buf = BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# AI insights prompt
# ---------------------------------------------------------------------------

def build_insights_prompt(data: dict, tax_rate: float) -> str:
    """Compact, numbers-only summary handed to the model — keeps the prompt small
    and stops the model from inventing figures that weren't in the data."""
    import json

    kpi, pnl = data["kpi"], data["pnl"]
    summary = {
        "kpis": {
            "net_sales": round(kpi["net_sales"], 2),
            "gross_profit": round(kpi["gross_profit"], 2),
            "gp_margin_pct": kpi["gp_margin"],
            "ebitda": round(kpi["ebitda"], 2),
            "ebitda_margin_pct": kpi["ebitda_margin"],
            "net_profit": round(kpi["net_profit"], 2),
            "np_margin_pct": kpi["np_margin"],
            "units_sold": round(kpi["units_sold"], 2),
            "inventory_value": round(kpi["inventory_value"], 2) if kpi["has_stock"] else None,
            "sell_through_pct": kpi["sell_through_pct"] if kpi["has_stock"] else None,
            "stock_alerts_count": kpi["stock_alerts_count"],
            "assumed_tax_rate_pct": round(tax_rate * 100),
        },
        "monthly_trend": {
            "months": data["trend"]["labels"],
            "net_sales": data["trend"]["net_sales"],
        } if data["trend"]["labels"] else None,
        "category_performance": [
            {"category": c["category"], "net_sales": round(c["net_sales"], 2),
             "gp_margin_pct": c["gp_margin"], "share_of_sales_pct": c["share_pct"]}
            for c in data["category_performance"]
        ],
        "top_products": [
            {"product": p["product"], "category": p["category"], "net_sales": round(p["net_sales"], 2),
             "np_margin_pct": p["np_margin"]}
            for p in data["top_products"][:8]
        ],
        "stock_alerts": [
            {"product": s["product"], "category": s["category"], "stock_qty": s["stock_qty"]}
            for s in data["stock_alerts"][:10]
        ],
    }

    return f"""You are a business analyst reviewing an MIS dashboard for a manufacturing/sales business. \
Base every claim strictly on the JSON data below — never invent numbers, competitors, or market names that \
aren't implied by the categories given. If the data is too thin for a section, say so briefly instead of \
guessing.

DATA:
{json.dumps(summary, indent=2)}

Respond in exactly these four short sections, using markdown headers (####) and concise bullet points \
(3-5 bullets per section, no fluff):

#### KPIs to watch closely
Which of the metrics above most need monitoring right now, and why (e.g. thin margins, declining trend, \
concentration risk in one category/product).

#### Where output/volume could improve
Practical suggestions to grow units sold or sell-through, grounded in what the category/product/stock data \
actually shows (e.g. products with strong margin but low volume, categories with high stock and low sell-through).

#### Where to focus investment
Based only on the category performance figures given (margin % and share of sales), which category or \
categories look most worth doubling down on, and which look weakest. Do not invent geographic markets that \
aren't in the data — talk about product/category segments instead unless the data includes real market/region info.

#### Risks & data gaps
Anything in the numbers that looks risky (e.g. stock alerts, thin margins, only one month of data) and what \
additional data would make this analysis more reliable.
"""
