# UABAMS Cloud

Cloud-side reference app for the Unattended Axle Box Acceleration Measurement
System. It includes gateway upload APIs, validation, alerting, calibration,
threshold settings, TMS export, and a React monitoring dashboard.

## Tech Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, Recharts
- Backend: FastAPI, SQLAlchemy
- Local database: SQLite, stored in your OS temp folder
- Cloud database: PostgreSQL through `DATABASE_URL`
- Deployment: Render blueprint in `render.yaml`

Docker is not required for this version of the project.

## Project Structure

```text
backend/
  app/                 FastAPI app, routers, models, services
  scripts/             Gateway simulator
  requirements.txt     Python dependencies
frontend/
  src/                 React app
  package.json         Frontend dependencies and scripts
render.yaml            Render deployment blueprint
```

## Run Locally

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at:

- http://localhost:8000
- http://localhost:8000/docs

On first startup, the backend creates a SQLite database under your OS temp
folder, for example
`C:\Users\Pilabs\AppData\Local\Temp\uabams-cloud\uabams.db` on this machine,
and seeds demo data.

### Frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The dashboard runs at http://localhost:5173 and calls the backend at
http://localhost:8000 by default.

## Optional Environment Files

You can copy the examples if you want explicit local configuration:

```bash
copy backend\.env.example backend\.env
copy frontend\.env.example frontend\.env
```

Important variables:

- `DATABASE_URL`: defaults to an SQLite database in your OS temp folder
- `CORS_ORIGINS`: defaults to `*`
- `SEED_ON_STARTUP`: defaults to `true`
- `VITE_API_BASE_URL`: defaults to `http://localhost:8000`

## Deploy To Render

1. Push the project to GitHub.
2. In Render, create a new Blueprint from this repository.
3. Render provisions PostgreSQL, runs the FastAPI backend, and builds the
   frontend static site.
4. Set `VITE_API_BASE_URL` to the live backend URL if you change the service
   name from the default in `render.yaml`.

## Main API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Backend health check |
| `GET` | `/api/v1/dashboard` | Dashboard data |
| `POST` | `/api/v1/archive` | Upload a gateway archive/demo payload |
| `GET`/`POST` | `/api/v1/threshold` | Threshold settings |
| `GET`/`POST` | `/api/v1/calibration` | Calibration history |
| `GET` | `/api/v1/alerts` | Alerts |
| `GET` | `/api/v1/gateways` | Gateway status |
| `GET` | `/api/v1/export/tms` | TMS export ZIP |

## Gateway Simulator

After the backend is running:

```bash
cd backend
venv\Scripts\activate
python scripts\gateway_simulator.py --url http://localhost:8000 --interval 5
```
