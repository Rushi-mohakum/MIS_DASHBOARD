# MIS Dashboard

Run it, upload a data file, get a Sales / Inventory / P&L dashboard — with a
downloadable Excel report and AI-generated business insights. No database,
no accounts, no fixed company setup — anyone can run this and point it at
their own Excel/CSV/PDF/Word data.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Open **http://localhost:5050**, upload a file, and the dashboard renders immediately.
Nothing is written to permanent storage — each upload is cached in a temp folder
only for the duration of your session (so Download and AI Insights can reuse it),
and is never sent anywhere except to the AI Insights feature if you use it.

## AI Insights setup

The dashboard includes a "Generate Insights" button that sends your computed
KPIs (not the raw file — just the numbers already shown on the dashboard) to
Google Gemini and asks for: which KPIs to watch, where output/volume could
improve, and where to focus investment, based only on the data you uploaded.

To enable it, set an API key as an environment variable before running the app:

```bash
export GEMINI_API_KEY=your-key-here      # Mac/Linux  
set GEMINI_API_KEY=your-key-here         # Windows (cmd)
$env:GEMINI_API_KEY="your-key-here"      # Windows (PowerShell)
```

Get a **free** key at **aistudio.google.com** — no credit card required, just
a Google account. Click "Get API key" → "Create API key". The free tier
(Gemini 2.5 Flash) is generous enough for regular personal use of this
dashboard. Without a key set, the dashboard still works fully — the AI
Insights button will just show a message explaining how to enable it.

## Download

- **Download Excel Report** — a formatted 6-sheet workbook (Summary, P&L
  Snapshot, Top Products, Category Performance, Monthly Trend, Inventory Alerts)
  regenerated fresh from your uploaded data.
- **Print / Save PDF** — uses the browser's print dialog with a print-friendly
  stylesheet (hides buttons/AI panel, switches to a light background) — choose
  "Save as PDF" as the destination in the print dialog for a PDF snapshot.

## Supported files

- **.xlsx / .xls / .csv** — most reliable. Read directly as a table.
- **.pdf** — the app looks for a real data table inside the PDF (via `pdfplumber`).
  Scanned/image-only PDFs won't work.
- **.docx** — the app looks for a Word table (via `python-docx`).

## Recommended columns

Column names are matched case-insensitively and a lot of common variants are
auto-detected (e.g. `qty`, `units`, `quantity` all map to units sold). Nothing
is required — missing columns just default to zero/blank and the dashboard
tells you what it filled in.

| Canonical column | Accepted variants | Used for |
|---|---|---|
| `date` | entry_date, month, order_date, transaction_date, period | monthly trend chart, month-over-month growth badge |
| `product` | item, item_name, sku, product_name | grouping, top products table |
| `category` | product_category, type, segment, department | category mix donut, category performance table |
| `units_sold` | qty, quantity, units, qty_sold, sold_qty | units sold KPI, sell-through |
| `unit_price` | price, rate, selling_price, mrp | computes net_sales if net_sales isn't given directly |
| `net_sales` | sales, revenue, total_sales, amount, gross_sales | Net Sales KPI (or derived from unit_price × units_sold) |
| `unit_cost` | cost, cost_price, cogs_per_unit, purchase_price | computes cogs if cogs isn't given directly |
| `cogs` | cost_of_goods_sold, total_cost | Gross Profit calculation |
| `opex` | operating_expense(s), expenses | EBITDA calculation (optional, defaults to 0) |
| `stock_qty` | stock, inventory, current_stock, closing_stock, on_hand | Inventory Value, Sell-Through, Stock Alerts |
| `reorder_level` | reorder_point, min_stock, safety_stock | Stock Alerts (optional; defaults to 0) |

A sample file that works out of the box is included at `sample_data/sample_sales_data.xlsx`.

## Assumptions in the P&L

Because a generic upload rarely includes a full accounting breakdown, the app
makes some simplifying assumptions, shown as a note under the P&L chart:

- **Gross Sales = Net Sales** (no returns/discounts data)
- **EBIT = PBT = EBITDA** (no depreciation or interest data)
- **Net Profit = PBT × (1 − tax rate)**, where you set the tax rate on the upload screen (default 25%)

If your data includes real `opex`, these numbers will reflect it. Everything
else is derived purely from units, price, and cost. The AI Insights feature is
told about these same assumptions and instructed not to invent numbers or
markets beyond what's in your data.
