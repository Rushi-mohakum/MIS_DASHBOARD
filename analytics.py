"""Data-quality, cleaning, chart-builder, and deterministic dataset-Q&A helpers."""
from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)
    return value


def build_quality_report(df: pd.DataFrame) -> dict:
    rows, columns = df.shape
    total_cells = rows * columns
    missing_total = int(df.isna().sum().sum())
    duplicates = int(df.duplicated().sum())
    duplicate_cells = duplicates * columns
    penalty = missing_total + duplicate_cells
    score = round(max(0.0, 100.0 - ((penalty / total_cells) * 100 if total_cells else 100.0)), 1)

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = [c for c in df.columns if c not in numeric_cols]

    column_quality = []
    for col in df.columns:
        series = df[col]
        missing = int(series.isna().sum())
        unique = int(series.nunique(dropna=True))
        column_quality.append({
            "column": str(col),
            "dtype": str(series.dtype),
            "missing": missing,
            "missing_pct": round((missing / rows * 100) if rows else 0, 1),
            "unique": unique,
        })

    missing_sorted = sorted(
        (item for item in column_quality if item["missing"] > 0),
        key=lambda item: item["missing"],
        reverse=True,
    )[:12]

    numeric_summary = []
    if numeric_cols:
        described = df[numeric_cols].describe().T.reset_index(names="column")
        for _, row in described.head(12).iterrows():
            numeric_summary.append({
                "column": str(row["column"]),
                "count": _json_value(round(float(row.get("count", 0)), 2)),
                "mean": _json_value(round(float(row.get("mean", 0)), 2)),
                "min": _json_value(round(float(row.get("min", 0)), 2)),
                "max": _json_value(round(float(row.get("max", 0)), 2)),
                "std": _json_value(round(float(row.get("std", 0)), 2)),
            })

    corr_labels: list[str] = []
    corr_values: list[list[float | None]] = []
    if len(numeric_cols) >= 2:
        corr_cols = numeric_cols[:8]
        corr = df[corr_cols].corr(numeric_only=True)
        corr_labels = [str(c) for c in corr.columns]
        corr_values = [
            [_json_value(round(float(v), 3)) for v in corr.loc[row].tolist()]
            for row in corr.index
        ]

    return {
        "rows": rows,
        "columns": columns,
        "total_cells": total_cells,
        "missing": missing_total,
        "missing_pct": round((missing_total / total_cells * 100) if total_cells else 0, 2),
        "duplicates": duplicates,
        "duplicate_pct": round((duplicates / rows * 100) if rows else 0, 2),
        "numeric": len(numeric_cols),
        "categorical": len(categorical_cols),
        "score": score,
        "column_quality": column_quality,
        "missing_columns": missing_sorted,
        "numeric_summary": numeric_summary,
        "numeric_columns": [str(c) for c in numeric_cols],
        "categorical_columns": [str(c) for c in categorical_cols],
        "correlation_labels": corr_labels,
        "correlation_values": corr_values,
    }


def clean_dataframe(df: pd.DataFrame, action: str) -> tuple[pd.DataFrame, str]:
    cleaned = df.copy()
    before_rows = len(cleaned)
    before_missing = int(cleaned.isna().sum().sum())

    if action == "remove_duplicates":
        cleaned = cleaned.drop_duplicates().reset_index(drop=True)
        return cleaned, f"Removed {before_rows - len(cleaned):,} duplicate rows."

    if action in {"fill_mean", "fill_median"}:
        numeric = cleaned.select_dtypes(include="number").columns
        for col in numeric:
            fill_value = cleaned[col].mean() if action == "fill_mean" else cleaned[col].median()
            if pd.notna(fill_value):
                cleaned[col] = cleaned[col].fillna(fill_value)
        filled = before_missing - int(cleaned.isna().sum().sum())
        method = "mean" if action == "fill_mean" else "median"
        return cleaned, f"Filled {filled:,} numeric missing values using the {method}."

    if action == "fill_mode":
        for col in cleaned.columns:
            mode = cleaned[col].mode(dropna=True)
            if not mode.empty:
                cleaned[col] = cleaned[col].fillna(mode.iloc[0])
        filled = before_missing - int(cleaned.isna().sum().sum())
        return cleaned, f"Filled {filled:,} missing values using the most frequent value in each column."

    if action == "drop_missing":
        cleaned = cleaned.dropna().reset_index(drop=True)
        return cleaned, f"Removed {before_rows - len(cleaned):,} rows containing missing values."

    if action == "standardize_text":
        text_cols = cleaned.select_dtypes(include=["object", "string"]).columns
        for col in text_cols:
            cleaned[col] = cleaned[col].map(lambda value: value.strip() if isinstance(value, str) else value)
        return cleaned, f"Trimmed extra spaces in {len(text_cols)} text columns."

    raise ValueError("Unknown cleaning action.")


def build_chart_series(df: pd.DataFrame, x: str, y: str, aggregation: str) -> dict:
    if x not in df.columns:
        raise ValueError("Select a valid X-axis column.")
    if aggregation not in {"sum", "mean", "count", "min", "max"}:
        aggregation = "sum"

    work = df[[x] + ([y] if y and y in df.columns and y != x else [])].copy()
    work = work.dropna(subset=[x])

    if aggregation == "count" or not y or y not in work.columns:
        grouped = work.groupby(x, dropna=False).size().sort_values(ascending=False).head(30)
        y_label = "Record Count"
    else:
        work[y] = pd.to_numeric(work[y], errors="coerce")
        work = work.dropna(subset=[y])
        grouped = getattr(work.groupby(x, dropna=False)[y], aggregation)().sort_values(ascending=False).head(30)
        y_label = f"{aggregation.title()} of {y}"

    return {
        "labels": [str(v) for v in grouped.index.tolist()],
        "values": [_json_value(round(float(v), 3)) for v in grouped.tolist()],
        "x_label": str(x),
        "y_label": y_label,
    }


def deterministic_dataset_answer(question: str, data: dict, quality: dict) -> str | None:
    q = re.sub(r"\s+", " ", question.lower()).strip()
    kpi = data["kpi"]
    products = data.get("top_products", [])
    categories = data.get("category_performance", [])

    def money(value: float) -> str:
        value = float(value)
        if abs(value) >= 10_000_000:
            return f"₹{value / 10_000_000:.2f} Cr"
        if abs(value) >= 100_000:
            return f"₹{value / 100_000:.2f} L"
        return f"₹{value:,.2f}"

    if any(term in q for term in ["highest net sales", "top product", "best selling product", "highest sales product"]):
        if products:
            p = products[0]
            return f"{p['product']} has the highest net sales at {money(p['net_sales'])}, with {p['units_sold']:,.0f} units sold."

    if "top 5" in q and "product" in q:
        if products:
            lines = [f"{i + 1}. {p['product']}: {money(p['net_sales'])}" for i, p in enumerate(products[:5])]
            return "Top five products by net sales:\n" + "\n".join(lines)

    if "top category" in q or "highest category" in q or "best category" in q:
        if categories:
            c = categories[0]
            return f"{c['category']} is the leading category with {money(c['net_sales'])} in net sales and {c['share_pct']}% of total sales."

    if "total net sales" in q or q in {"net sales", "what are net sales"}:
        return f"Total net sales are {money(kpi['net_sales'])}."
    if "gross profit" in q:
        return f"Gross profit is {money(kpi['gross_profit'])}, with a gross-profit margin of {kpi['gp_margin']}%."
    if "ebitda" in q:
        return f"EBITDA is {money(kpi['ebitda'])}, with an EBITDA margin of {kpi['ebitda_margin']}%."
    if "net profit" in q:
        return f"Net profit is {money(kpi['net_profit'])}, with a net-profit margin of {kpi['np_margin']}%."
    if "inventory value" in q:
        if kpi["has_stock"]:
            return f"Estimated inventory value is {money(kpi['inventory_value'])}."
        return "Inventory value cannot be calculated because the uploaded dataset has no usable stock quantity data."
    if "units sold" in q:
        return f"Total units sold are {kpi['units_sold']:,.0f}."
    if "missing" in q:
        return f"The active dataset contains {quality['missing']:,} missing values, representing {quality['missing_pct']}% of all cells."
    if "duplicate" in q:
        return f"The active dataset contains {quality['duplicates']:,} duplicate rows, representing {quality['duplicate_pct']}% of rows."
    if "quality score" in q or "data quality" in q:
        return f"The current data-quality score is {quality['score']}/100."
    if "stock alert" in q or "reorder" in q:
        return f"There are {kpi['stock_alerts_count']} products at or below their reorder level."
    return None


def build_ai_dataset_context(df: pd.DataFrame, data: dict, quality: dict) -> str:
    numeric = df.select_dtypes(include="number")
    numeric_stats = {}
    if not numeric.empty:
        desc = numeric.describe().T[["count", "mean", "min", "max"]].round(2)
        numeric_stats = desc.head(15).to_dict(orient="index")

    sample = df.head(8).copy()
    for col in sample.columns:
        sample[col] = sample[col].map(_json_value)

    payload = {
        "dataset_shape": {"rows": quality["rows"], "columns": quality["columns"]},
        "columns": [{"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns],
        "data_quality": {
            "score": quality["score"],
            "missing": quality["missing"],
            "duplicates": quality["duplicates"],
        },
        "business_kpis": data["kpi"],
        "top_products": data.get("top_products", [])[:8],
        "category_performance": data.get("category_performance", [])[:8],
        "monthly_trend": data.get("trend", {}),
        "numeric_statistics": numeric_stats,
        "sample_rows": sample.to_dict(orient="records"),
    }
    import json
    return json.dumps(payload, default=str, ensure_ascii=False)
