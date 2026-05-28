<<<<<<< HEAD
# BreatheESG — Emissions Data Ingestion & Review Platform

Live demo: **[deployed-url]**  
Login: `analyst` / `demo1234`

## What this is

A Django REST + React prototype that ingests emissions data from three enterprise source types, normalises it, and surfaces a review dashboard where analysts can inspect, flag, approve, and lock records for audit.

---

## Architecture

```
backend/         Django 4.2 + DRF + JWT auth
  ingestion/
    models.py    Data model (Tenant, IngestionBatch, EmissionRecord, EditHistory)
    parsers.py   Three source parsers with validation logic
    views.py     REST API — upload, review, dashboard
    serializers.py
    management/commands/seed_demo.py

frontend/        React 18 + React Query + Recharts
  src/pages/
    DashboardPage.js   CO₂e overview, scope breakdown, trend chart
    ReviewPage.js      Analyst queue — filter, approve, reject, bulk actions
    UploadPage.js      File upload with validation rule summary

sample_data/
  SAP_MM_FuelProcurement_Q1_2025.csv
  Utility_Portal_Electricity_Q1_2025.csv
  Navan_TravelExport_Q1_2025.json

docs/
  MODEL.md       Data model decisions (read this first)
  DECISIONS.md   Every ambiguity resolved
  TRADEOFFS.md   Three things deliberately not built
  SOURCES.md     Real-world format research per source
```

---

## Running locally

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo   # Creates demo tenant, users, sample records
python manage.py runserver
```

API available at `http://localhost:8000/api/`

### Frontend

```bash
cd frontend
npm install
npm start
```

App at `http://localhost:3000`

---

## Deploying to Render

1. Create a new **Web Service** from this repo
2. Set **Root Directory** to `backend`
3. **Build command:** `pip install -r requirements.txt && python manage.py migrate && python manage.py seed_demo`
4. **Start command:** `gunicorn breathe_esg.wsgi`
5. Add environment variables:
   - `SECRET_KEY` — any random string
   - `DEBUG` — `False`
   - `DATABASE_URL` — Render Postgres connection string (add a Postgres DB in the dashboard)

For the frontend, deploy as a **Static Site**:
- **Root Directory:** `frontend`
- **Build command:** `npm install && npm run build`
- **Publish directory:** `build`
- **Environment variable:** `REACT_APP_API_URL=https://your-backend.onrender.com`

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/token/` | Login → JWT |
| GET | `/api/me/` | Current user + tenant |
| GET | `/api/dashboard/` | Stats, scope totals, trend |
| POST | `/api/ingestion/upload/` | Upload a source file |
| GET | `/api/ingestion/` | Batch history |
| GET | `/api/records/` | Paginated records (filterable) |
| POST | `/api/records/{id}/approve/` | Approve a record |
| POST | `/api/records/{id}/reject/` | Reject a record |
| POST | `/api/records/{id}/flag/` | Flag for attention |
| POST | `/api/records/{id}/lock/` | Lock approved record for audit |
| POST | `/api/records/bulk-approve/` | Bulk approve by IDs |
| GET | `/api/records/{id}/history/` | Edit history for a record |
| GET | `/api/facilities/` | Plant lookup table |

---

## Data sources — what's realistic about them

See `docs/SOURCES.md` for full research notes. Summary:

| Source | Format chosen | Key realistic issues modelled |
|---|---|---|
| SAP fuel/procurement | Flat file CSV (MB51 report) | German headers, mixed units (L/LTR/Liters), YYYY/MM/DD dates, duplicate PO, missing plant |
| Electricity | Utility portal CSV | Overlapping billing periods, estimated reads, missing meter ID, mixed unit casing |
| Corporate travel | Navan/Concur JSON | Cancelled bookings skipped, null distance → airport lookup, multi-leg flights, same-origin test bookings |

---

## Grading traceability

| Criterion | Where to look |
|---|---|
| Data model quality (35%) | `docs/MODEL.md`, `ingestion/models.py` |
| Decision defence (25%) | `docs/DECISIONS.md` |
| Source realism (20%) | `docs/SOURCES.md`, `sample_data/`, `ingestion/parsers.py` |
| Analyst UX (10%) | `ReviewPage.js`, `DashboardPage.js` |
| Tradeoffs (10%) | `docs/TRADEOFFS.md` |
=======
# BreatheESG-Assignment
Enterprise ESG emissions ingestion and analytics platform
>>>>>>> 7d31457430f96f736ef6f418390f183b9d79e787
