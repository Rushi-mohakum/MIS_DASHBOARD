"""Automatic workbook classification and production analytics for MIS Intelligence Studio."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import pandas as pd


SHEET_HEADER_ROWS = {
    "info": 1,
    "dwm": 3,
    "sch": 1,
    "mold": 0,
    "plan": 1,
    "atte": 1,
    "inspection": 1,
    "prodeff": 1,
    "production": 3,
    "inspeefficiency": 1,
    "sale": 0,
    "sales": 0,
    "deflashing": 0,
    "incident": 4,
    "msebreading": 5,
    "pareto": 2,
}

PRODUCTION_SHEET_WEIGHTS = {
    "production": 6,
    "prodeff": 3,
    "inspection": 2,
    "inspefficiency": 2,
    "plan": 2,
    "mold": 1,
    "deflashing": 1,
    "pareto": 1,
    "atte": 1,
    "incident": 1,
    "msebreading": 1,
    "dwm": 1,
    "sch": 1,
}

HEADER_HINTS = [
    "date", "plant", "shift", "oee", "target production", "target prod",
    "ok production", "total production", "m/c no", "machine", "no. of shots",
    "rejection", "operator", "downtime", "mold", "material required",
    "actual material use", "customer", "invoice", "quantity", "net sales",
    "revenue", "sales", "product", "stock", "dispatch", "efficiency",
]


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _sheet_key(value: Any) -> str:
    key = _norm(value)
    if key.endswith("sheet"):
        key = key[:-5]
    return key


def _row_score(values) -> int:
    score = 0
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if not text or text.lower().startswith("unnamed"):
            continue
        normalized = _norm(text)
        if any(_norm(hint) == normalized for hint in HEADER_HINTS):
            score += 2
        elif any(_norm(hint) in normalized for hint in HEADER_HINTS if len(_norm(hint)) >= 5):
            score += 1
    return score


def _find_header_row(raw: pd.DataFrame, sheet_name: str) -> int:
    if raw is None or raw.empty:
        return 0
    key = _sheet_key(sheet_name)
    preferred = SHEET_HEADER_ROWS.get(key)
    if preferred is not None and preferred < len(raw):
        preferred_values = raw.iloc[preferred].tolist()
        date_headers = sum(isinstance(v, (datetime, date, pd.Timestamp)) for v in preferred_values if not pd.isna(v))
        if _row_score(preferred_values) >= 2 or date_headers >= 3 or key in SHEET_HEADER_ROWS:
            return preferred

    best_row = 0
    best_score = -1
    for idx in range(min(12, len(raw))):
        values = raw.iloc[idx].tolist()
        score = _row_score(values)
        nonempty = sum(1 for v in values if not pd.isna(v) and str(v).strip())
        score += min(nonempty, 12) * 0.02
        if score > best_score:
            best_row, best_score = idx, score

    if best_score <= 0 and preferred is not None and preferred < len(raw):
        return preferred
    return best_row


def _clean_header(value: Any, index: int):
    if pd.isna(value) or not str(value).strip() or str(value).strip().lower().startswith("unnamed"):
        return f"Column {index + 1}"
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value
    return str(value).strip()


def _unique_headers(values) -> list[Any]:
    output = []
    counts = {}
    for index, value in enumerate(values):
        header = _clean_header(value, index)
        key = str(header)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 1:
            header = f"{key}.{counts[key] - 1}"
        output.append(header)
    return output


def load_excel_workbook(path: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Read each workbook sheet once, returning both raw and headered frames."""
    raw_sheets = pd.read_excel(path, sheet_name=None, header=None)
    sheets: dict[str, pd.DataFrame] = {}
    for name, raw in raw_sheets.items():
        if raw is None or raw.empty:
            continue
        # Preserve blank rows until header detection because some factory templates
        # intentionally place titles / notes above the real header row.
        raw = raw.dropna(axis=1, how="all")
        if raw.empty:
            continue
        header_idx = _find_header_row(raw, name)
        headers = _unique_headers(raw.iloc[header_idx].tolist())
        frame = raw.iloc[header_idx + 1:].copy()
        frame.columns = headers
        frame = frame.dropna(how="all").dropna(axis=1, how="all")
        if not frame.empty:
            sheets[str(name)] = frame.reset_index(drop=True)
    return sheets, raw_sheets


def detect_workbook_type(sheets: dict[str, pd.DataFrame], raw_sheets: dict[str, pd.DataFrame] | None = None) -> dict:
    """Classify a workbook by sheet names and detected headers, not filename alone."""
    names = list((raw_sheets or {}).keys()) or list(sheets.keys())
    normalized_names = [_sheet_key(name) for name in names]

    production_name_score = sum(
        weight for name, weight in PRODUCTION_SHEET_WEIGHTS.items()
        if any(name == item or name in item or item in name for item in normalized_names)
    )
    production_headers = set()
    sales_headers = set()
    for frame in sheets.values():
        for col in frame.columns:
            normalized = _norm(col)
            if any(term in normalized for term in [
                "oee", "targetprod", "okproduction", "totalproduction", "mcno",
                "machineno", "machine", "nosho", "downtime", "actualmaterialuse",
                "materialrequired", "plant", "shift", "rejection", "moldno", "cavities",
            ]):
                production_headers.add(normalized)
            if any(term in normalized for term in [
                "invoiceno", "customer", "netsales", "revenue", "sales", "quantity",
                "product", "category", "unitsold", "unitprice", "unitcost", "stockqty",
                "reorderlevel", "cogs", "opex", "invoice",
            ]):
                sales_headers.add(normalized)

    has_main_production_sheet = any("production" == name or name.endswith("production") for name in normalized_names)
    production_score = production_name_score + min(len(production_headers), 10)
    sales_name_score = 3 if any(name in {"sale", "sales", "invoices", "invoice"} for name in normalized_names) else 0
    sales_score = sales_name_score + min(len(sales_headers), 6)

    # A strong production signature wins even when the workbook also contains a "sale" tab.
    if has_main_production_sheet or production_score >= 7:
        kind = "production"
        confidence = "high" if has_main_production_sheet or production_score >= 10 else "medium"
    elif production_score >= 4 and production_score > sales_score:
        kind = "production"
        confidence = "medium"
    elif sales_score >= 3:
        kind = "business"
        confidence = "high" if sales_name_score or sales_score >= 5 else "medium"
    else:
        kind = "business"
        confidence = "low"

    return {
        "type": kind,
        "confidence": confidence,
        "production_score": int(production_score),
        "sales_score": int(sales_score),
        "sheet_count": len(sheets),
    }


def _find_sheet(sheets: dict[str, pd.DataFrame], aliases: list[str]) -> pd.DataFrame | None:
    normalized = {_sheet_key(name): frame for name, frame in sheets.items()}
    for alias in aliases:
        key = _sheet_key(alias)
        if key in normalized:
            return normalized[key]
    for alias in aliases:
        key = _sheet_key(alias)
        for name, frame in normalized.items():
            if key and key in name:
                return frame
    return None


def _find_col(frame: pd.DataFrame | None, aliases: list[str]):
    if frame is None or frame.empty:
        return None
    columns = list(frame.columns)
    # Prefer the literal header first. This matters for workbooks with repeated summary columns.
    for alias in aliases:
        for col in columns:
            if str(col).strip() == alias:
                return col
    for alias in aliases:
        target = _norm(alias)
        for col in columns:
            if _norm(col) == target:
                return col
    for alias in aliases:
        target = _norm(alias)
        if len(target) < 4:
            continue
        for col in columns:
            if target in _norm(col):
                return col
    return None


def _numeric(frame: pd.DataFrame | None, aliases: list[str], index=None) -> pd.Series:
    if index is None:
        index = frame.index if frame is not None else pd.RangeIndex(0)
    col = _find_col(frame, aliases)
    if frame is None or col is None:
        return pd.Series(0.0, index=index, dtype="float64")
    return pd.to_numeric(frame[col], errors="coerce").reindex(index).fillna(0.0)


def _text(frame: pd.DataFrame | None, aliases: list[str], index=None, default="Unknown") -> pd.Series:
    if index is None:
        index = frame.index if frame is not None else pd.RangeIndex(0)
    col = _find_col(frame, aliases)
    if frame is None or col is None:
        return pd.Series(default, index=index, dtype="object")
    values = frame[col].reindex(index)
    values = values.astype("object")
    return values.where(values.notna() & values.astype(str).str.strip().ne(""), default).astype(str)


def _json_records(records: list[dict]) -> list[dict]:
    cleaned = []
    for record in records:
        row = {}
        for key, value in record.items():
            if pd.isna(value):
                row[key] = None
            elif isinstance(value, (datetime, date, pd.Timestamp)):
                row[key] = pd.Timestamp(value).strftime("%Y-%m-%d")
            elif hasattr(value, "item"):
                row[key] = value.item()
            else:
                row[key] = value
        cleaned.append(row)
    return cleaned


def _series_records(grouped: pd.DataFrame, label_col: str, fields: list[tuple[str, str]], limit: int = 12) -> list[dict]:
    if grouped.empty:
        return []
    return _json_records(grouped.head(limit).to_dict("records"))


def _safe_sum(series: pd.Series) -> float:
    try:
        return float(pd.to_numeric(series, errors="coerce").fillna(0).clip(lower=0).sum())
    except Exception:
        return 0.0


def _fmt_date(value) -> str:
    try:
        return pd.Timestamp(value).strftime("%d %b %Y")
    except Exception:
        return "Unknown"


def build_production_dashboard_data(sheets: dict[str, pd.DataFrame], filename: str = "") -> dict:
    """Build KPIs and chart series from a multi-sheet production workbook."""
    warnings: list[str] = []
    main = _find_sheet(sheets, ["production", "daily production", "molding report"])
    if main is None:
        # Fall back to the sheet with the strongest production-column signature.
        candidates = []
        for name, frame in sheets.items():
            score = sum(_find_col(frame, [header]) is not None for header in [
                "Plant", "Date", "Total production", "Ok production", "OEE", "M/C no"
            ])
            candidates.append((score, frame))
        main = max(candidates, key=lambda item: item[0])[1] if candidates else pd.DataFrame()
        warnings.append("A dedicated production sheet was not found. Analytics use the closest matching worksheet.")

    if main is None or main.empty:
        return {"ok": False, "error": "No usable production worksheet was found.", "warnings": warnings}

    frame = main.copy()
    date_col = _find_col(frame, ["Date", "Production Date", "Entry Date"])
    if date_col is not None:
        dates = pd.to_datetime(frame[date_col], errors="coerce")
    else:
        dates = pd.Series(pd.NaT, index=frame.index)
        warnings.append("No production date column was detected. Trend charts may be unavailable.")

    total_primary_col = _find_col(frame, ["Total production"])
    total_alternate_col = _find_col(frame, ["TOTAL PRODUCTION", "Total Production Qty", "Production Qty"])
    if total_primary_col is not None:
        total = pd.to_numeric(frame[total_primary_col], errors="coerce").fillna(0).clip(lower=0)
    elif total_alternate_col is not None:
        total = pd.to_numeric(frame[total_alternate_col], errors="coerce").fillna(0).clip(lower=0)
    else:
        total = _numeric(frame, ["Production", "Quantity Produced", "Total Qty"], frame.index).clip(lower=0)

    ok_col = _find_col(frame, ["Ok production", "OK production", "Good production", "OK Qty"])
    if ok_col is None:
        ok_col = _find_col(frame, ["Ok", "OK"])
    ok = pd.to_numeric(frame[ok_col], errors="coerce").fillna(0).clip(lower=0) if ok_col is not None else pd.Series(0.0, index=frame.index)

    target_col = _find_col(frame, ["Target prod.", "Target production", "Production target", "Target Qty"])
    target = pd.to_numeric(frame[target_col], errors="coerce").fillna(0).clip(lower=0) if target_col is not None else pd.Series(0.0, index=frame.index)
    reject_col = _find_col(frame, ["Parts  Qty rejected", "Parts Qty rejected", "Rejected Qty", "Total Rejection"])
    reject_derived = (total - ok).clip(lower=0)
    if reject_col is not None:
        reject_direct = pd.to_numeric(frame[reject_col], errors="coerce").fillna(0).clip(lower=0)
        rejected = reject_direct if reject_direct.sum() > 0 else reject_derived
    else:
        rejected = reject_derived

    oee_col = _find_col(frame, ["OEE"])
    oee_raw = pd.to_numeric(frame[oee_col], errors="coerce") if oee_col is not None else pd.Series(float("nan"), index=frame.index)
    oee_valid = oee_raw[(oee_raw >= 0) & (oee_raw <= 1.1)]
    oee_mean = float(oee_valid.mean()) if not oee_valid.empty else 0.0

    plant = _text(frame, ["Plant", "Plant Name"], frame.index, "Unknown Plant")
    machine = _text(frame, ["M/C no", "MC no", "Machine No", "Machine"], frame.index, "Unknown Machine")
    shift = _text(frame, ["Shift"], frame.index, "Unknown Shift")
    operator = _text(frame, ["M/c Operator name", "Operator name", "Operator"], frame.index, "")
    inspector = _text(frame, ["QA Inspector", "Inspector"], frame.index, "")
    material_used = _numeric(frame, ["Actual material use", "Actual Material Used", "Material Used"], frame.index).clip(lower=0)
    material_required = _numeric(frame, ["Material Required", "Material Required Qty", "Planned Material"], frame.index).clip(lower=0)

    work = pd.DataFrame({
        "_date": dates,
        "_plant": plant,
        "_machine": machine,
        "_shift": shift,
        "_total": total,
        "_ok": ok,
        "_target": target,
        "_rejected": rejected,
        "_oee": oee_raw,
        "_material_used": material_used,
        "_material_required": material_required,
        "_operator": operator,
        "_inspector": inspector,
    }, index=frame.index)
    work = work[work["_date"].notna() & ((work["_total"] > 0) | (work["_ok"] > 0) | (work["_target"] > 0) | (work["_rejected"] > 0))].copy()
    if work.empty:
        # Keep rows that contain output even when a source date is missing.
        work = pd.DataFrame({
            "_date": dates,
            "_plant": plant,
            "_machine": machine,
            "_shift": shift,
            "_total": total,
            "_ok": ok,
            "_target": target,
            "_rejected": rejected,
            "_oee": oee_raw,
            "_material_used": material_used,
            "_material_required": material_required,
            "_operator": operator,
            "_inspector": inspector,
        }, index=frame.index)
        work = work[(work["_total"] > 0) | (work["_ok"] > 0) | (work["_target"] > 0) | (work["_rejected"] > 0)].copy()

    total_qty = _safe_sum(work["_total"])
    ok_qty = _safe_sum(work["_ok"])
    rejected_qty = _safe_sum(work["_rejected"])
    target_qty = _safe_sum(work["_target"])
    achievement = round(total_qty / target_qty * 100, 1) if target_qty else 0.0
    rejection_pct = round(rejected_qty / total_qty * 100, 2) if total_qty else 0.0

    period_dates = work["_date"].dropna()
    period_label = "Period not available"
    if not period_dates.empty:
        start, end = period_dates.min(), period_dates.max()
        period_label = _fmt_date(start) if start == end else f"{_fmt_date(start)} – {_fmt_date(end)}"

    trend = {"labels": [], "total": [], "ok": [], "rejected": [], "target": []}
    dated_work = work.dropna(subset=["_date"]).copy()
    if not dated_work.empty:
        dated_work["_day"] = pd.to_datetime(dated_work["_date"]).dt.normalize()
        by_day = dated_work.groupby("_day", dropna=True).agg(
            total=("_total", "sum"), ok=("_ok", "sum"), rejected=("_rejected", "sum"), target=("_target", "sum")
        ).sort_index().tail(31)
        trend = {
            "labels": [pd.Timestamp(d).strftime("%d %b") for d in by_day.index],
            "total": [round(float(v), 2) for v in by_day["total"]],
            "ok": [round(float(v), 2) for v in by_day["ok"]],
            "rejected": [round(float(v), 2) for v in by_day["rejected"]],
            "target": [round(float(v), 2) for v in by_day["target"]],
        }

    plant_roll = work[work["_plant"].astype(str).str.strip().ne("Unknown Plant")].groupby("_plant", dropna=False).agg(
        total=("_total", "sum"), ok=("_ok", "sum"), rejected=("_rejected", "sum"),
        target=("_target", "sum"), oee=("_oee", "mean")
    ).reset_index().sort_values("total", ascending=False)
    plant_roll["oee"] = plant_roll["oee"].where((plant_roll["oee"] >= 0) & (plant_roll["oee"] <= 1.1), 0)
    # Recompute OEE by plant from valid readings only to avoid invalid formula results.
    plant_labels, plant_oee = [], []
    for name, group in work.groupby("_plant", dropna=False):
        values = group["_oee"]
        values = values[(values >= 0) & (values <= 1.1)]
        plant_labels.append(str(name))
        plant_oee.append(round(float(values.mean() * 100), 1) if not values.empty else None)
    plant_oee_map = dict(zip(plant_labels, plant_oee))
    plant_data = {
        "labels": [str(v) for v in plant_roll["_plant"].tolist()],
        "total": [round(float(v), 2) for v in plant_roll["total"].tolist()],
        "ok": [round(float(v), 2) for v in plant_roll["ok"].tolist()],
        "rejected": [round(float(v), 2) for v in plant_roll["rejected"].tolist()],
        "target": [round(float(v), 2) if target_qty > 0 else None for v in plant_roll["target"].tolist()],
        "oee": [plant_oee_map.get(str(v)) for v in plant_roll["_plant"].tolist()],
    }

    machine_roll = work.groupby("_machine", dropna=False).agg(
        total=("_total", "sum"), ok=("_ok", "sum"), target=("_target", "sum"),
        rejected=("_rejected", "sum"), oee=("_oee", "mean")
    ).reset_index()
    machine_roll = machine_roll[machine_roll["_machine"].astype(str).str.strip().ne("")]
    machine_roll = machine_roll.sort_values("total", ascending=False).head(10)
    machine_roll["oee"] = machine_roll["oee"].where((machine_roll["oee"] >= 0) & (machine_roll["oee"] <= 1.1))
    machines = [
        {"machine": str(r["_machine"]), "total": round(float(r["total"]), 2), "ok": round(float(r["ok"]), 2),
         "target": round(float(r["target"]), 2) if target_qty > 0 else None, "rejected": round(float(r["rejected"]), 2),
         "oee_pct": round(float(r["oee"]) * 100, 1) if pd.notna(r["oee"]) else None}
        for _, r in machine_roll.iterrows()
    ]

    shift_roll = work.groupby("_shift", dropna=False)["_total"].sum().sort_values(ascending=False)
    shift_data = {"labels": [str(v) for v in shift_roll.index], "total": [round(float(v), 2) for v in shift_roll.values]}

    # Quality defects are taken from the inspection worksheet, not inferred from text labels.
    inspection = _find_sheet(sheets, ["Inspection", "Quality Inspection"])
    defect_names = [
        ("Rework / Flash", ["Rework / Flash"]),
        ("Hole Block", ["Hole Block"]),
        ("Short Mould", ["Short Mould", "Short Mold"]),
        ("Cut / Damage", ["Cut/ Damage", "Cut / Damage"]),
        ("Burn Mark", ["Burn Mark"]),
        ("Weld Line", ["Weld Line"]),
        ("Bubble", ["Bubble"]),
        ("Color Variation", ["Color variation"]),
        ("Cut While Deflashing", ["Cut While Deflashing"]),
        ("Leg Cut", ["Leg Cut"]),
        ("Foreign Particle", ["Foreign Particle"]),
        ("Catching on Surface", ["Catching on surface"]),
        ("Insert Open", ["Insert Open"]),
        ("Insert Missing", ["Insert Missing " , "Insert Missing"]),
        ("Rubber Tear", ["Rubber Tear"]),
    ]
    defects = []
    if inspection is not None:
        for label, aliases in defect_names:
            col = _find_col(inspection, aliases)
            if col is None:
                continue
            value = pd.to_numeric(inspection[col], errors="coerce").fillna(0).clip(lower=0).sum()
            if value > 0:
                defects.append({"defect": label, "qty": round(float(value), 2)})
    defects.sort(key=lambda item: item["qty"], reverse=True)
    if not defects:
        warnings.append("No numeric defect counts were detected in the Inspection worksheet.")

    pareto_sheet = _find_sheet(sheets, ["Pareto", "Product Pareto"])
    pareto_products = []
    if pareto_sheet is not None:
        p_product = _find_col(pareto_sheet, ["Product", "Part No", "Vibes Part No"])
        p_total = _find_col(pareto_sheet, ["Production", "Total Production"])
        p_reject = _find_col(pareto_sheet, ["Total Reject", "Rejected Qty", "Rejection"])
        if p_product is not None:
            temp = pd.DataFrame({
                "product": pareto_sheet[p_product].astype(str),
                "production": pd.to_numeric(pareto_sheet[p_total], errors="coerce").fillna(0) if p_total else 0,
                "rejected": pd.to_numeric(pareto_sheet[p_reject], errors="coerce").fillna(0) if p_reject else 0,
            })
            temp = temp[temp["product"].str.strip().ne("") & temp["product"].str.lower().ne("nan")]
            temp = temp[pd.to_numeric(temp["production"], errors="coerce").fillna(0) > 0].head(10)
            pareto_products = _json_records(temp.to_dict("records"))

    operator_names = set()
    for series in [work["_operator"], work["_inspector"]]:
        operator_names.update(str(value).strip() for value in series if str(value).strip() and str(value).strip().lower() not in {"", "unknown", "nan", "none"})
    operator_efficiency = []
    efficiency_sheet = _find_sheet(sheets, ["Inspe Efficiency", "Inspection Efficiency", "Prod Eff"])
    if efficiency_sheet is not None:
        op_col = _find_col(efficiency_sheet, ["Operator name", "Operator"])
        eff_col = _find_col(efficiency_sheet, ["Efficiency", "Total Efficiency"])
        if op_col is not None and eff_col is not None:
            eff_frame = pd.DataFrame({
                "operator": efficiency_sheet[op_col].astype(str),
                "efficiency": pd.to_numeric(efficiency_sheet[eff_col], errors="coerce"),
            })
            eff_frame = eff_frame[
                eff_frame["operator"].str.strip().ne("") &
                eff_frame["operator"].str.lower().ne("nan") &
                eff_frame["efficiency"].between(0, 1.5)
            ]
            if not eff_frame.empty:
                eff_frame = eff_frame.groupby("operator", as_index=False)["efficiency"].mean()
                eff_frame["efficiency_pct"] = eff_frame["efficiency"] * 100
                operator_efficiency = [
                    {"operator": str(r["operator"]), "efficiency_pct": round(float(r["efficiency_pct"]), 1)}
                    for _, r in eff_frame.sort_values("efficiency_pct", ascending=False).head(10).iterrows()
                ]

    # Planning and mold masters.
    plan_sheet = _find_sheet(sheets, ["Plan", "Production Plan"])
    planned_shots = _safe_sum(_numeric(plan_sheet, ["Planned Shot", "Target Shot", "Planned Shots"])) if plan_sheet is not None else 0.0
    plan_material = _safe_sum(_numeric(plan_sheet, ["material required", "Material Required Qty"])) if plan_sheet is not None else 0.0
    plan_production = _safe_sum(_numeric(plan_sheet, ["Production", "Planned Production"])) if plan_sheet is not None else 0.0

    mold_sheet = _find_sheet(sheets, ["Mold", "Mould"])
    mold_count = 0
    cavity_avg = 0.0
    if mold_sheet is not None:
        mold_col = _find_col(mold_sheet, ["Mold no", "Mould no", "Mold No."])
        cavity_col = _find_col(mold_sheet, ["Cavities", "Running ok cavities"])
        if mold_col is not None:
            mold_count = int(mold_sheet[mold_col].dropna().astype(str).str.strip().replace("", pd.NA).nunique())
        if cavity_col is not None:
            cav = pd.to_numeric(mold_sheet[cavity_col], errors="coerce")
            cav = cav[(cav > 0) & (cav < 10000)]
            cavity_avg = round(float(cav.mean()), 1) if not cav.empty else 0.0

    material_used_total = _safe_sum(work["_material_used"])
    material_required_total = _safe_sum(work["_material_required"])
    if material_required_total <= 0:
        material_required_total = plan_material
    material_variance_pct = round((material_used_total - material_required_total) / material_required_total * 100, 1) if material_required_total else 0.0

    # Downtime categories come from explicit machine / process downtime columns.
    downtime_aliases = [
        ("Machine Breakdown", ["M/C BD In Min", "Machine Breakdown"]),
        ("Mold Breakdown", ["Mold BD in Min", "Mould Breakdown"]),
        ("Material Not Available", ["Material NA in Min", "Material Not Available"]),
        ("Try-outs / Other", ["Try Outs / other in Min", "Try Outs"]),
        ("Heating Up", ["Heating up Time in Min", "Heating Up"]),
        ("Power Failure", ["Power failure in Min", "Power Failure"]),
        ("Trial", ["Trial in Min"]),
    ]
    downtime = []
    for label, aliases in downtime_aliases:
        value = _safe_sum(_numeric(frame, aliases, frame.index))
        if value > 0:
            downtime.append({"reason": label, "minutes": round(value, 2)})
    downtime.sort(key=lambda item: item["minutes"], reverse=True)
    downtime_total = sum(item["minutes"] for item in downtime)
    if downtime_total <= 0:
        downtime_total = _safe_sum(_numeric(frame, ["Downtime including set up", "Total Downtime"], frame.index))

    # Incidents, with no assumptions about a missing status column.
    incident_sheet = _find_sheet(sheets, ["INCIDENT", "Incident Monitoring"])
    incidents = []
    open_incidents = 0
    incident_count = 0
    incident_status_available = False
    if incident_sheet is not None:
        incident_date_col = _find_col(incident_sheet, ["Date of Incident", "Incident Date"])
        incident_type_col = _find_col(incident_sheet, ["Accident type", "Incident Type"])
        location_col = _find_col(incident_sheet, ["Department/Location", "Location"])
        status_col = _find_col(incident_sheet, ["Status (Open/ Closed)", "Status", "Incident Status"])
        for _, row in incident_sheet.iterrows():
            date_value = pd.to_datetime(row[incident_date_col], errors="coerce") if incident_date_col is not None else pd.NaT
            incident_type = str(row[incident_type_col]).strip() if incident_type_col is not None else ""
            if pd.isna(date_value) and (not incident_type or incident_type.lower() == "nan"):
                continue
            status_value = row[status_col] if status_col is not None else None
            status = str(status_value).strip() if status_value is not None else "Not recorded"
            if status_col is not None and pd.notna(status_value) and status.lower() not in {"", "nan", "none"}:
                incident_status_available = True
                if status.lower() == "open":
                    open_incidents += 1
            incident_count += 1
            incidents.append({
                "date": _fmt_date(date_value) if not pd.isna(date_value) else "Date not recorded",
                "type": incident_type if incident_type and incident_type.lower() != "nan" else "Unclassified",
                "location": str(row[location_col]).strip() if location_col is not None and pd.notna(row[location_col]) else "Not recorded",
                "status": status if status and status.lower() != "nan" else "Not recorded",
            })
        incidents = incidents[:12]

    # Attendance sheet: use the most recent dated column if the workbook has one.
    attendance = {"available": False, "date": None, "present": 0, "listed": 0}
    attendance_sheet = _find_sheet(sheets, ["Atte", "Attendance"])
    if attendance_sheet is not None:
        date_columns = []
        for col in attendance_sheet.columns:
            parsed = pd.to_datetime(str(col), errors="coerce")
            if not pd.isna(parsed):
                date_columns.append((pd.Timestamp(parsed), col))
        if date_columns:
            latest_date, latest_col = max(date_columns, key=lambda item: item[0])
            values = pd.to_numeric(attendance_sheet[latest_col], errors="coerce")
            attendance = {
                "available": True,
                "date": latest_date.strftime("%d %b %Y"),
                "present": int((values > 0).sum()),
                "listed": int(values.notna().sum()),
            }

    # Energy readings sheet: only calculate if explicit used-unit columns exist.
    energy_sheet = _find_sheet(sheets, ["MSEB reading", "Energy", "Electricity"])
    energy = {"available": False, "labels": [], "usage": [], "latest_total": 0.0, "latest_date": None}
    if energy_sheet is not None:
        energy_date_col = _find_col(energy_sheet, ["Date"])
        used_cols = []
        for col in energy_sheet.columns:
            normalized = _norm(col)
            if "usedunit" in normalized or normalized in {"unit1", "unit2", "unit3"}:
                used_cols.append(col)
        if energy_date_col is not None and used_cols:
            energy_frame = pd.DataFrame({"date": pd.to_datetime(energy_sheet[energy_date_col], errors="coerce")})
            energy_frame["usage"] = sum(
                (pd.to_numeric(energy_sheet[col], errors="coerce").fillna(0).clip(lower=0) for col in used_cols),
                start=pd.Series(0.0, index=energy_sheet.index),
            )
            energy_frame = energy_frame.dropna(subset=["date"]).groupby("date", as_index=False)["usage"].sum().sort_values("date").tail(31)
            if not energy_frame.empty and float(energy_frame["usage"].sum()) > 0:
                energy = {
                    "available": True,
                    "labels": [pd.Timestamp(d).strftime("%d %b") for d in energy_frame["date"]],
                    "usage": [round(float(v), 2) for v in energy_frame["usage"]],
                    "latest_total": round(float(energy_frame.iloc[-1]["usage"]), 2),
                    "latest_date": _fmt_date(energy_frame.iloc[-1]["date"]),
                }
            elif not energy_frame.empty:
                warnings.append("The energy worksheet has dated rows, but used-unit fields contain no positive values. The energy chart is withheld rather than treating blanks or formula outputs as confirmed zero consumption.")

    # Schedule / stock indicators from the SCH. worksheet.
    schedule = {"available": False, "dispatch_balance": 0.0, "production_pending": 0.0, "inspection_pending": 0.0, "stock": 0.0}
    schedule_sheet = _find_sheet(sheets, ["SCH.", "Schedule", "Stock"])
    if schedule_sheet is not None:
        schedule = {
            "available": True,
            "dispatch_balance": _safe_sum(_numeric(schedule_sheet, ["Dispatch Balance", "Dispatch balance"])),
            "production_pending": _safe_sum(_numeric(schedule_sheet, ["prod pending", "Production Pending"])),
            "inspection_pending": _safe_sum(_numeric(schedule_sheet, ["Inspection pending", "Inspection Pending"])),
            "stock": _safe_sum(_numeric(schedule_sheet, ["Stock", "Closing Stock"])),
        }

    kpi = {
        "total_production": round(total_qty, 2),
        "ok_production": round(ok_qty, 2),
        "rejected_qty": round(rejected_qty, 2),
        "production_target": round(target_qty, 2),
        "achievement_pct": achievement,
        "rejection_pct": rejection_pct,
        "oee_pct": round(oee_mean * 100, 1),
        "workforce_count": len(operator_names),
        "machine_count": int(work["_machine"].replace("Unknown Machine", pd.NA).dropna().nunique()),
        "plant_count": int(work["_plant"].replace("Unknown Plant", pd.NA).dropna().nunique()),
        "downtime_minutes": round(downtime_total, 2),
        "material_used": round(material_used_total, 2),
        "material_required": round(material_required_total, 2),
        "material_variance_pct": material_variance_pct,
        "incident_count": incident_count,
        "open_incidents": open_incidents,
        "mold_count": mold_count,
        "average_cavities": cavity_avg,
        "planned_shots": round(planned_shots, 2),
        "plan_production": round(plan_production, 2),
        "quality_ppm": round(rejected_qty / total_qty * 1_000_000, 1) if total_qty else 0,
    }

    metric_status = {
        "production": total_qty > 0,
        "ok_production": ok_qty > 0,
        "rejection": rejected_qty > 0 or total_qty > 0,
        "target": target_qty > 0,
        "oee": not oee_valid.empty,
        "material": material_used_total > 0 or material_required_total > 0,
        "workforce": bool(operator_names),
    }

    if _find_sheet(sheets, ["Prod Eff", "Production Efficiency"]) is None:
        warnings.append("No Prod Eff worksheet was detected. Machine metrics are based on the production log.")
    if plan_sheet is None:
        warnings.append("No Plan worksheet was detected. Planning metrics are limited to production targets.")
    if energy_sheet is None:
        warnings.append("No energy readings worksheet was detected.")
    elif not energy["available"]:
        energy_date_col = _find_col(energy_sheet, ["Date"])
        used_unit_columns = [
            col for col in energy_sheet.columns
            if "usedunit" in _norm(col) or _norm(col) in {"unit1", "unit2", "unit3"}
        ]
        if energy_date_col is None or not used_unit_columns:
            warnings.append("Energy chart unavailable: a dated column and explicit Used Unit columns are required.")

    return {
        "ok": True,
        "filename": filename,
        "period_label": period_label,
        "sheet_count": len(sheets),
        "sheet_names": list(sheets.keys()),
        "warnings": list(dict.fromkeys(warnings)),
        "kpi": kpi,
        "trend": trend,
        "plant": plant_data,
        "machines": machines,
        "shift": shift_data,
        "defects": defects[:12],
        "pareto_products": pareto_products,
        "operators": operator_efficiency,
        "downtime": downtime,
        "incidents": incidents,
        "attendance": attendance,
        "energy": energy,
        "schedule": schedule,
        "metric_status": metric_status,
        "module_status": {
            "quality": inspection is not None,
            "workforce": bool(operator_names),
            "planning": plan_sheet is not None or target_qty > 0,
            "molds": mold_sheet is not None,
            "energy": energy_sheet is not None,
            "incidents": incident_sheet is not None,
            "incident_status": incident_status_available,
        },
    }
