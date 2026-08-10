"""AI helpers with a reliable rule-based fallback when no API key is configured."""
from __future__ import annotations

import os

from analytics import build_ai_dataset_context, deterministic_dataset_answer
from parser import build_insights_prompt


def rule_based_insights(data: dict, quality: dict) -> str:
    kpi = data["kpi"]
    products = data.get("top_products", [])
    categories = data.get("category_performance", [])
    momentum = data.get("momentum", {})

    bullets_watch = [
        f"Data quality is {quality['score']}/100, with {quality['missing']:,} missing values and {quality['duplicates']:,} duplicate rows.",
        f"Gross-profit margin is {kpi['gp_margin']}%, EBITDA margin is {kpi['ebitda_margin']}%, and net-profit margin is {kpi['np_margin']}%.",
    ]
    if momentum.get("net_sales_growth_pct") is not None:
        direction = "increased" if momentum["net_sales_growth_pct"] >= 0 else "decreased"
        bullets_watch.append(
            f"Net sales {direction} by {abs(momentum['net_sales_growth_pct'])}% from {momentum['prev_month']} to {momentum['last_month']}."
        )
    if kpi["has_stock"]:
        bullets_watch.append(
            f"Sell-through is {kpi['sell_through_pct']}%, with {kpi['stock_alerts_count']} stock alerts requiring review."
        )

    output = ["#### KPIs to watch closely"] + [f"- {b}" for b in bullets_watch[:5]]
    output.append("\n#### Where output/volume could improve")
    if products:
        output.append(f"- Prioritise {products[0]['product']}, currently the leading product by net sales.")
        low_margin = sorted(products, key=lambda p: p.get("np_margin", 0))[:2]
        for p in low_margin:
            output.append(f"- Review pricing and cost structure for {p['product']}, which has a {p['np_margin']}% net-profit margin.")
    else:
        output.append("- Add product and unit-volume columns to identify specific output opportunities.")

    output.append("\n#### Where to focus investment")
    if categories:
        top = categories[0]
        output.append(
            f"- {top['category']} leads with {top['share_pct']}% of sales and a {top['gp_margin']}% gross-profit margin."
        )
        strongest_margin = max(categories, key=lambda c: c.get("gp_margin", 0))
        if strongest_margin["category"] != top["category"]:
            output.append(
                f"- {strongest_margin['category']} has the strongest gross-profit margin at {strongest_margin['gp_margin']}%; validate whether volume can scale."
            )
    else:
        output.append("- Add category data to compare investment opportunities by business segment.")

    output.append("\n#### Risks & data gaps")
    if quality["missing"]:
        output.append(f"- Resolve {quality['missing']:,} missing values before using the dataset for formal management reporting.")
    if quality["duplicates"]:
        output.append(f"- Remove {quality['duplicates']:,} duplicate rows to prevent overstated totals.")
    if not data["trend"].get("labels"):
        output.append("- No reliable date trend is available; add a transaction or reporting date column.")
    risk_count = 0
    if quality["missing"]:
        risk_count += 1
    if quality["duplicates"]:
        risk_count += 1
    if not data["trend"].get("labels"):
        risk_count += 1
    if not kpi["has_stock"]:
        output.append("- Stock quantity and unit-cost data are needed for inventory valuation and reorder analysis.")
        risk_count += 1
    if risk_count == 0:
        output.append("- No material structural data-quality gaps were detected in the active dataset.")
    return "\n".join(output)


def _gemini_text(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    from google import genai

    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    interaction = client.interactions.create(model=model, input=prompt)
    text = getattr(interaction, "output_text", None)
    if not text:
        raise RuntimeError("Gemini returned an empty response.")
    return text.strip()


def generate_insights(data: dict, quality: dict, tax_rate: float) -> tuple[str, str]:
    if not os.environ.get("GEMINI_API_KEY"):
        return rule_based_insights(data, quality), "rule-based"

    prompt = build_insights_prompt(data, tax_rate)
    prompt += (
        "\n\nDATA QUALITY:\n"
        f"Score: {quality['score']}/100; missing values: {quality['missing']}; "
        f"duplicate rows: {quality['duplicates']}. Mention material quality risks in the final section."
    )
    try:
        return _gemini_text(prompt), "gemini"
    except Exception:
        return rule_based_insights(data, quality), "rule-based fallback"


def answer_dataset_question(df, question: str, data: dict, quality: dict) -> tuple[str, str]:
    direct = deterministic_dataset_answer(question, data, quality)
    if direct:
        return direct, "calculated"

    if not os.environ.get("GEMINI_API_KEY"):
        return (
            "I can answer calculated questions about sales, products, categories, profit, inventory, missing values, duplicates, and data quality. "
            "Configure GEMINI_API_KEY on Render for broader natural-language questions.",
            "local",
        )

    context = build_ai_dataset_context(df, data, quality)
    prompt = f"""You are an MIS data analyst. Answer the user's question using only the supplied dataset context.
Do not invent values. When a calculation cannot be supported by the context, clearly state what additional column or data is required.
Keep the answer concise and management-friendly.

DATASET CONTEXT:
{context}

USER QUESTION:
{question}
"""
    try:
        return _gemini_text(prompt), "gemini"
    except Exception as exc:
        return f"AI chat could not complete the request: {exc}", "error"
