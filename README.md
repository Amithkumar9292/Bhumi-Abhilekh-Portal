# भूमि अभिलेख पोर्टल — Bhumi Abhilekh Portal

> **Intelligent Land Record Digitization and Validation System**  
> Government of India · Ministry of Rural Development  
> ⚠️ **DEMO SYSTEM — All data is synthetic. Not legally binding.**

---

## 📋 Overview

A production-quality, full-stack land record digitization platform built for Indian government use cases. It provides an intelligent 11-stage document processing pipeline, configurable validation engine, GIS/cadastral map integration, multilingual support for 22 languages (8th Schedule), and complete audit trail.

### Key Features

| Feature | Description |
|---|---|
| **11-Stage Pipeline** | OCR → Field Extraction → Classification → Confidence Scoring → Validation → Duplicate Detection → Anomaly Detection |
| **22 Languages** | Complete 8th Schedule support with Google Fonts, RTL (Urdu), persistent preference |
| **Validation Engine** | 10 configurable rules, cross-record consistency, duplicate detection |
| **GIS / Cadastral** | Interactive map with synthetic parcel polygons, state-aware bounding, spatial search |
| **RBAC** | ADMIN / OFFICER / VERIFIER / VIEWER roles with JWT authentication |
| **Integration Adapters** | DILRMP, LRMS (state), Bhuvan GIS, DORIS — mock mode with live-ready interfaces |
| **Audit Trail** | MongoDB-backed immutable event log for every sensitive action |
| **Analytics** | District/state digitization stats, OCR accuracy, validation health |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  React + TypeScript + Vite               │
│          (RBAC · i18n · RTL · Dark/Light theme)         │
└────────────────────────────┬────────────────────────────┘
                             │ REST API (OpenAPI/Swagger)
┌────────────────────────────▼────────────────────────────┐
│              FastAPI + Python (Async)                    │
│         JWT Auth · RBAC · Rate Limiting · Audit         │
├─────────────┬───────────────┬───────────────────────────┤
│  PostgreSQL │     Redis     │        MongoDB             │
│  (Primary)  │  (Cache/Jobs) │  (Audit/Document Logs)    │
└─────────────┴───────────────┴───────────────────────────┘
```

**Tech Stack:**
- **Frontend:** React 18, TypeScript, Vite, Zustand, React Query, Lucide React
- **Backend:** FastAPI, SQLAlchemy (async), Alembic, Pydantic v2
- **Databases:** PostgreSQL 16, Redis 7, MongoDB 7
- **Testing:** Vitest (frontend), pytest + pytest-asyncio (backend)
- **Deployment:** Docker Compose, Vercel (frontend), Dockerfile (backend)

---

## 🚀 Quick Start

### Prerequisites

- **Docker Desktop** (recommended) or:
  - Python 3.11+, Node.js 20+
  - PostgreSQL 16, Redis 7, MongoDB 7

### Option A: Docker Compose (Recommended)

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd LAND_Rec

# 2. Create environment file
cp .env.example .env
# Edit .env with your secrets (see Environment Variables below)

# 3. Start all services
docker compose up --build

# 4. Run migrations + seed demo data
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed.seed_data
docker compose exec backend python -m app.seed.seed_extended

# 5. Open browser
open http://localhost          # Frontend (Nginx)
open http://localhost:8000/docs # API Swagger UI
```

### Option B: Local Development

**Backend:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
pip install -r requirements-test.txt

# Start services (PostgreSQL, Redis, MongoDB must be running)
cp .env.example .env
alembic upgrade head
python -m app.seed.seed_data
python -m app.seed.seed_extended
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev         # http://localhost:5173
```

---

## 🔐 Demo Credentials

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin@1234` | ADMIN — full access |
| `officer_rajesh` | `Officer@1234` | OFFICER — create & manage records |
| `verifier_priya` | `Verifier@1234` | VERIFIER — review & approve |
| `viewer_anand` | `Viewer@1234` | VIEWER — read only |

---

## 🌐 Multilingual Support

The system supports **22 languages** from the **8th Schedule of the Constitution of India**:

| Code | Language | Script | RTL |
|---|---|---|---|
| `en` | English | Latin | — |
| `hi` | हिन्दी | Devanagari | — |
| `bn` | বাংলা | Bengali | — |
| `te` | తెలుగు | Telugu | — |
| `mr` | मराठी | Devanagari | — |
| `ta` | தமிழ் | Tamil | — |
| `gu` | ગુજરાતી | Gujarati | — |
| `kn` | ಕನ್ನಡ | Kannada | — |
| `ml` | മലയാളം | Malayalam | — |
| `pa` | ਪੰਜਾਬੀ | Gurmukhi | — |
| `or` | ଓଡ଼ିଆ | Oriya | — |
| `as` | অসমীয়া | Bengali | — |
| `ur` | اردو | Nastaliq | ✅ |
| `mai` | मैथिली | Devanagari | — |
| `sa` | संस्कृतम् | Devanagari | — |

Language preference persists in `localStorage`. Google Fonts are loaded on demand per language.

---

## 📂 Project Structure

```
LAND_Rec/
├── backend/
│   ├── app/
│   │   ├── models/          # SQLAlchemy ORM (User, LandRecord, Document, Pipeline, Extended)
│   │   ├── routers/         # FastAPI routers (auth, land_records, gis, validation, ...)
│   │   ├── services/        # Business logic (validation_engine, gis_service, ocr_service, ...)
│   │   ├── seed/            # Demo data seeders
│   │   ├── db/              # PostgreSQL, Redis, MongoDB connections
│   │   └── main.py          # FastAPI app entry point
│   ├── alembic/versions/    # Database migrations
│   ├── tests/               # pytest test suite
│   │   ├── auth/            # Auth & RBAC tests
│   │   ├── api/             # API endpoint tests
│   │   └── unit/            # Unit tests (validation, GIS, security, adapters)
│   ├── requirements.txt
│   ├── requirements-test.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── i18n/            # Translation system (22 languages)
│   │   ├── pages/           # Page components (12 modules)
│   │   ├── components/      # Shared UI components
│   │   ├── store/           # Zustand state (auth, UI)
│   │   ├── api/             # Axios API clients
│   │   └── tests/           # Vitest unit tests
│   ├── vercel.json          # Vercel deployment config
│   └── Dockerfile           # Nginx production image
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🧪 Running Tests

### Backend Tests
```bash
cd backend
pip install -r requirements-test.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific categories
pytest tests/auth/          # Auth & RBAC
pytest tests/api/           # API endpoints
pytest tests/unit/          # Unit tests (no DB required for most)

# Verbose output
pytest -v
```

### Frontend Tests
```bash
cd frontend

# Run once
npm test

# Watch mode (dev)
npm run test:watch

# Browser UI
npm run test:ui
```

---

## 🌍 Vercel Deployment (Frontend)

1. **Import** the `frontend/` directory into Vercel
2. **Set build command:** `npm run build`
3. **Set output directory:** `dist`
4. **Set environment variable:**
   ```
   VITE_API_BASE_URL=https://your-backend-api.example.com
   ```
5. The `vercel.json` handles SPA routing, asset caching, and security headers automatically

### Backend Deployment

Deploy the `backend/` as a Docker container to:
- **Railway** (`railway.app`) — easiest, supports Docker + env vars
- **Render** — free tier available
- **Google Cloud Run** — scale to zero
- **AWS ECS / Fargate** — production scale

Required environment variables:
```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/land_db
REDIS_URL=redis://host:6379/0
MONGODB_URL=mongodb://host:27017
SECRET_KEY=<strong-random-secret>
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
```

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# === Database ===
DATABASE_URL=postgresql+asyncpg://land_user:land_password@localhost:5432/land_records_db
REDIS_URL=redis://localhost:6379/0
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=land_audit_db

# === Security ===
SECRET_KEY=change-this-to-a-strong-random-secret-min-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# === App ===
ENVIRONMENT=development
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
MAX_UPLOAD_SIZE_MB=10
UPLOAD_DIR=uploads

# === Pipeline ===
OCR_CONFIDENCE_THRESHOLD=0.70
PIPELINE_ANOMALY_THRESHOLD=0.85

# === Integrations (optional) ===
DILRMP_API_KEY=
DILRMP_API_URL=https://api.dilrmp.gov.in/v2
BHUVAN_API_KEY=
```

---

## 📊 API Documentation

With the backend running, visit:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

### Key API Groups

| Group | Base Path | Description |
|---|---|---|
| Auth | `/api/v1/auth` | Login, logout, token refresh, me |
| Land Records | `/api/v1/land-records` | CRUD + extended (mutations, owners, survey) |
| Documents | `/api/v1/documents` | Upload, process, list |
| Pipeline | `/api/v1/pipeline` | Jobs, stages, anomalies, human review |
| Validation | `/api/v1/validation` | Run rules, results, rule management |
| GIS | `/api/v1/gis` | Map data, spatial search, coordinates |
| Analytics | `/api/v1/analytics` | KPIs, district stats, throughput |
| Audit | `/api/v1/audit` | Immutable event log |
| Integrations | `/api/v1/integrations` | DILRMP, LRMS, Bhuvan GIS adapters |
| Notifications | `/api/v1/notifications` | User notification inbox |

---

## 🔒 Security

- JWT access tokens (HS256, configurable expiry)
- Bcrypt password hashing
- Role-based access control on every protected endpoint
- Rate limiting on auth endpoints (slowapi)
- Input validation via Pydantic v2
- Audit log for every sensitive action (MongoDB)
- File upload validation (type, size, magic bytes)
- CORS restricted to configured origins
- Security headers (CSP, X-Frame-Options, etc.) via Vercel/Nginx

---

## 📌 License & Disclaimer

This is a **demonstration system** built for educational and evaluation purposes.

> ⚠️ **ALL DATA IS SYNTHETIC.** No real land records, personal information, or government data is used. This system is **NOT legally binding** and should not be used for official land registration, mutation, or registration purposes.

---

*Built with ❤️ for Digital India — Powered by Antigravity*
