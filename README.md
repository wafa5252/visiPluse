# VisiPulse — Predictive Health-Tech Hospital Monitoring System

A full-stack predictive maintenance platform for hospital equipment: IoT
telemetry ingestion → narrow-AI anomaly detection → human-in-the-loop
review → maintenance ticketing, with role-based access control and a
full audit trail.

```
visipulse/
├── backend/            FastAPI application
│   ├── app/
│   │   ├── main.py         entrypoint, middleware, security headers
│   │   ├── config.py       env-driven settings
│   │   ├── database.py     SQLAlchemy engine/session
│   │   ├── models.py       ORM schema (Device, SensorReading, AIPrediction, …)
│   │   ├── schemas.py      Pydantic request/response validation
│   │   ├── security.py     password hashing, JWT
│   │   ├── deps.py         auth dependency + RBAC guards
│   │   ├── audit.py        audit-log helper
│   │   ├── ai_engine.py    anomaly-detection / risk-scoring engine
│   │   └── routers/        one router per resource
│   ├── seed.py          demo data + one live worked example
│   └── requirements.txt
└── frontend/            Static dashboard (HTML + Tailwind CDN + vanilla JS)
    ├── login.html
    ├── index.html
    ├── app.js
    └── config.js         set API_BASE here
```

## 1. Architecture

**Predictive pipeline** (`sensors.py` → `ai_engine.py` → `predictions.py` → `tickets.py`):

1. A device or gateway posts telemetry to `POST /sensor-readings`.
2. `ai_engine.evaluate_and_maybe_create_prediction()` runs immediately in
   the same request: it compares the new reading against that device's
   recent rolling baseline per metric (temperature, voltage, pressure,
   cpu_load) using a z-score deviation model, with hard safety bounds as
   a floor so a single extreme first-ever reading is never missed even
   without history. If the composite risk score clears the configured
   threshold, an `AIPrediction` row is written with
   `requires_human_approval=True`.
3. A medical staff member or admin reviews pending predictions
   (`GET /predictions?status_filter=pending`) and calls
   `POST /predictions/{id}/decision`. The AI **never** auto-approves
   itself — every prediction sits in `pending` until a human accepts or
   rejects it.
4. On approval, a `MaintenanceTicket` can be opened automatically in the
   same transaction, pre-prioritized from the risk score, ready for a
   maintenance technician to pick up and update through
   `open → in_progress → resolved`.

The anomaly detector is intentionally a transparent statistical model
rather than an opaque model, so a human reviewer can reason about *why*
something was flagged before approving action on hospital equipment.
Swapping it for a trained model later only requires changing
`ai_engine.evaluate_device()` — no router code depends on its internals.

**Why the schema deviates slightly from the original DDL:** `User` /
`MaintenanceTicket` gained `created_by` and `assigned_to` foreign keys,
and `AIPrediction` gained `approval_status` and `approved_by`, because a
governance system that requires human approval needs to record *who*
approved *what* — the original schema tracked the boolean flag but not
the accountability trail. An `AuditLog` table was added for the same
reason: NCA ECC-style compliance needs an event-level trail, not just
current-state tables.

## 2. Security & compliance notes (NCA ECC-oriented)

- **RBAC** — three roles (`admin`, `medical_staff`, `maintenance_tech`)
  enforced server-side via FastAPI dependencies (`deps.require_roles`),
  not just hidden in the UI. Every router explicitly states which roles
  may call it.
- **Authentication** — JWT bearer tokens (`python-jose`), bcrypt password
  hashing (`passlib`), 60-minute token expiry by default.
- **Audit logging** — every login (success and failure), device change,
  telemetry ingestion, AI prediction, approval/rejection, and ticket
  change writes an `AuditLog` row in the same DB transaction as the
  change itself, so the trail can't silently drift from reality. Only
  admins can read `/audit`.
- **Input validation** — every write endpoint takes a Pydantic model with
  explicit types, length limits, and numeric bounds (e.g. `cpu_load`
  0–100); FastAPI rejects malformed payloads before they reach any
  handler.
- **Transport & headers** — CORS is locked to an explicit origin
  allow-list (`CORS_ORIGINS` env var); every response carries
  `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`,
  and HSTS headers. HSTS assumes TLS termination in front of the app
  (nginx / load balancer) in production — this app does not terminate
  TLS itself.
- **Brute-force protection** — a simple in-memory rate limiter caps
  `/auth/login` at 10 attempts/minute per client IP. Swap for a
  Redis-backed limiter for a multi-instance deployment.
- **Least-privilege by design** — technicians can execute tickets but
  cannot approve the AI's own risk assessment; only medical staff/admins
  can. This mirrors segregation-of-duties expectations in a clinical
  environment.

**What's out of scope / next steps for a real production rollout:**
Alembic migrations (currently `create_all` on startup, fine for a demo,
not for schema evolution), MFA, secrets manager integration instead of
`.env`, a real IoT gateway auth scheme (device certs / mTLS instead of
user JWTs for the ingestion endpoint), and a WAF/reverse proxy in front
of the API.

## 3. Running it locally

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate      # optional but recommended
pip install -r requirements.txt
cp .env.example .env                                  # then edit JWT_SECRET_KEY
python seed.py                                         # creates demo users + sample telemetry
uvicorn app.main:app --reload --port 8000
```
API docs (dev only): http://localhost:8000/docs

### Frontend
```bash
cd frontend
python -m http.server 4173
```
Open http://localhost:4173/login.html — sign in with one of the seeded
accounts printed by `seed.py`. If you change the backend port/host,
update `API_BASE` in `frontend/config.js`, and add the frontend's origin
to `CORS_ORIGINS` in `backend/.env`.

### Demo accounts (created by `seed.py`)
| Username    | Password       | Role              |
|-------------|----------------|-------------------|
| admin       | AdminPass123   | admin             |
| dr.hana     | ClinicPass123  | medical_staff     |
| tech.omar   | TechPass123    | maintenance_tech  |

The seed script also injects one out-of-range telemetry reading on the
MRI scanner so a real pending AI prediction is waiting for you to review
on first login — sign in as `dr.hana` or `admin` and open **AI
Predictions** to try the approval flow end-to-end.

## 4. Extending it

- **Swap the AI model**: edit `ai_engine.evaluate_device()` — return the
  same `AnomalyResult` shape and everything downstream keeps working.
- **Add a role**: extend `models.UserRole`, then reference it in the
  relevant router's `require_roles(...)` call.
- **Move to MySQL**: set `DATABASE_URL` in `.env` to a
  `mysql+pymysql://...` URL — the code already supports it (`PyMySQL` is
  in `requirements.txt`).
- **Real IoT ingestion**: replace the `INGEST_ROLES` guard on
  `POST /sensor-readings` with a service-credential/device-cert scheme
  instead of a human-role check.
