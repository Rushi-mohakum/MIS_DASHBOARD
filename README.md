# MIS Intelligence Studio

A Flask-based MIS and data-analysis dashboard that combines the original MIS Dashboard with selected InsightForge-AI capabilities in a vibrant gradient interface.

## Included features

- CSV, Excel, PDF-table and Word-table upload
- Automatic mapping of common sales, product, category, profit and inventory columns
- Sales, P&L, product, category and inventory dashboards
- Data-quality score, missing-value analysis, duplicates, column profiling and correlations
- Reversible data-cleaning actions with a session history
- Custom chart builder
- Calculated dataset chat for common MIS questions
- Gemini-powered insights and broader chat when `GEMINI_API_KEY` is configured
- Rule-based AI fallback when no API key is available
- PDF, Excel, cleaned CSV and cleaned Excel downloads
- Render health-check endpoint at `/health`

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5050`.

## Environment variables

```env
MIS_SECRET_KEY=replace-with-a-long-random-value
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL=gemini-3.6-flash
```

`GEMINI_API_KEY` is optional. Calculated MIS questions and rule-based management insights work without it.

## Render configuration

Use these values in the existing Render web service:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0:$PORT --workers 2 --threads 4 --timeout 120`
- Health check path: `/health`
- Auto-Deploy: `On Commit`
- Branch: `main`

After pushing a commit to the linked `main` branch, Render should rebuild and deploy automatically when Auto-Deploy is enabled.

## Git update

Copy these files into the existing `MIS-Dashboard` repository, then run:

```bash
git add .
git commit -m "Build MIS Intelligence Studio vibrant gradient dashboard"
git push origin main
```

## Current storage behavior

Uploaded files are held in a temporary server-side session cache. A Render restart can clear the active dataset. Persistent MySQL upload history, user login and role permissions are planned for Phase 2.
