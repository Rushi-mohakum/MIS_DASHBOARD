"""
MIS Dashboard — upload a data file, get an instant Sales / Inventory / P&L dashboard,
download it as a formatted Excel report, and generate AI-written business insights.

Run with:  python app.py
Then open: http://localhost:5050
"""
import os
import pickle
import tempfile
import uuid

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session

from parser import load_dataframe, compute_dashboard_data, build_excel_report, build_ppt_report, build_insights_prompt

app = Flask(__name__)
app.secret_key = os.environ.get("MIS_SECRET_KEY", "mis-dashboard-local-secret")

ALLOWED_EXT = {"xlsx", "xls", "csv", "pdf", "docx"}

# Server-side cache for the last-parsed dataset per browser session, so Download
# and AI Insights can reuse it without re-uploading. Local single-user tool, so
# a temp-dir + small token in the session cookie is enough — nothing persists
# after the process restarts.
CACHE_DIR = os.path.join(tempfile.gettempdir(), "mis_dashboard_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(token):
    return os.path.join(CACHE_DIR, f"{token}.pkl")


def _save_to_cache(df, tax_rate):
    token = uuid.uuid4().hex
    with open(_cache_path(token), "wb") as f:
        pickle.dump({"df": df, "tax_rate": tax_rate}, f)
    session["dataset_token"] = token


def _load_from_cache():
    token = session.get("dataset_token")
    if not token:
        return None
    path = _cache_path(token)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@app.route("/", methods=["GET"])
def upload_page():
    return render_template("upload.html", has_api_key=bool(os.environ.get("GEMINI_API_KEY")))


@app.route("/dashboard", methods=["POST"])
def dashboard():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Please choose a file to upload.", "error")
        return redirect(url_for("upload_page"))

    if not allowed_file(file.filename):
        flash("Unsupported file type. Please upload .xlsx, .xls, .csv, .pdf, or .docx", "error")
        return redirect(url_for("upload_page"))

    try:
        tax_rate = float(request.form.get("tax_rate") or 25) / 100
    except ValueError:
        tax_rate = 0.25

    ext = file.filename.rsplit(".", 1)[1].lower()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix="." + ext) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
        df, warnings = load_dataframe(tmp_path, ext)
    except Exception as e:
        flash(f"Could not read that file: {e}", "error")
        return redirect(url_for("upload_page"))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if df is None or df.empty:
        flash(
            "No usable tabular data found in that file. Try an Excel/CSV file with columns like "
            "product, category, units_sold, net_sales (or unit_price), cogs (or unit_cost), stock_qty.",
            "error",
        )
        return redirect(url_for("upload_page"))

    data = compute_dashboard_data(df, tax_rate=tax_rate)
    _save_to_cache(df, tax_rate)

    return render_template(
        "dashboard.html",
        data=data,
        filename=file.filename,
        warnings=warnings,
        tax_rate=round(tax_rate * 100),
        row_count=len(df),
        has_api_key=bool(os.environ.get("GEMINI_API_KEY")),
    )


@app.route("/download/xlsx", methods=["GET"])
def download_xlsx():
    cached = _load_from_cache()
    if not cached:
        flash("Your session has expired — please upload the file again.", "error")
        return redirect(url_for("upload_page"))

    data = compute_dashboard_data(cached["df"], tax_rate=cached["tax_rate"])
    buf = build_excel_report(cached["df"], data, cached["tax_rate"])
    return send_file(
        buf, as_attachment=True, download_name="MIS_Dashboard_Report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/download/pptx", methods=["GET"])
def download_pptx():
    cached = _load_from_cache()
    if not cached:
        flash("Your session has expired — please upload the file again.", "error")
        return redirect(url_for("upload_page"))

    data = compute_dashboard_data(cached["df"], tax_rate=cached["tax_rate"])
    buf = build_ppt_report(cached["df"], data, cached["tax_rate"])
    return send_file(
        buf, as_attachment=True, download_name="MIS_Dashboard_Report.pptx",
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


@app.route("/insights", methods=["POST"])
def insights():
    cached = _load_from_cache()
    if not cached:
        return jsonify({"ok": False, "error": "Your session has expired — please re-upload your file."}), 400

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return jsonify({
            "ok": False,
            "error": "No GEMINI_API_KEY found. Set it as an environment variable to enable AI Insights "
                     "(see README.md — 'AI Insights setup'). Get a free key at aistudio.google.com.",
        }), 400

    try:
        import google.generativeai as genai
    except ImportError:
        return jsonify({"ok": False, "error": "The 'google-generativeai' package isn't installed. Run: pip install google-generativeai"}), 500

    data = compute_dashboard_data(cached["df"], tax_rate=cached["tax_rate"])
    prompt = build_insights_prompt(data, cached["tax_rate"])

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.5-flash")
        resp = model.generate_content(prompt)
        text = resp.text
    except Exception as e:
        return jsonify({"ok": False, "error": f"AI Insights request failed: {e}"}), 500

    return jsonify({"ok": True, "text": text})


if __name__ == "__main__":
    app.run(debug=True, port=5050, use_reloader=False)