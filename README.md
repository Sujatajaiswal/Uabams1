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
- `ALERT_NOTIFICATION_WEBHOOK_URL`: optional SMS/notification gateway endpoint
- `ALERT_NOTIFICATION_BEARER_TOKEN`: optional bearer token for that endpoint
- `TMS_DELIVERY_MODE`: `local` by default, or `http` for direct CRIS/TMS API push
- `TMS_HTTP_URL`: CRIS/TMS receiving endpoint when `TMS_DELIVERY_MODE=http`
- `TMS_HTTP_BEARER_TOKEN`: optional bearer token for the CRIS/TMS endpoint
- `TMS_LOCAL_EXPORT_DIR`: local/audit folder for generated TMS ZIP files

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
| `PUT`/`POST` | `/api/v1/archive` | Upload a real gateway ZIP archive or JSON demo payload |
| `GET`/`POST` | `/api/v1/threshold` | Threshold settings |
| `GET`/`POST` | `/api/v1/calibration` | Calibration history |
| `GET` | `/api/v1/alerts` | Alerts |
| `GET` | `/api/v1/gateways` | Gateway status |
| `GET` | `/api/v1/export/tms` | TMS export ZIP |
| `POST` | `/api/v1/export/tms/deliver` | Build and deliver/audit the TMS export |
| `GET` | `/api/v1/maintenance/notification-deliveries` | SMS/notification outbox audit |
| `GET` | `/api/v1/maintenance/tms-deliveries` | CRIS/TMS delivery audit |

## Gateway Simulator

After the backend is running:

```bash
cd backend
venv\Scripts\activate
python scripts\gateway_simulator.py --url http://localhost:8000 --interval 5
```

## Gateway ZIP Storage

The cloud endpoint now supports the ICD gateway archive format:

```text
session_metadata.json
rms/rms_25cm.bin
peak/peak_50m.bin
faults/faults.bin
raw/adxl_left.bin
raw/adxl_right.bin
raw/bogie.bin
raw/encoder.bin
```

Original ZIPs and extracted binary files are preserved unchanged under
`ARCHIVE_STORAGE_DIR`, which defaults to the OS temp folder:

```text
C:\Users\Pilabs\AppData\Local\Temp\uabams-cloud\archives
```

The parsed records are stored in SQLite/PostgreSQL tables:
`archives`, `extracted_files`, `rms_records`, `peak_records`,
`fault_records`, plus dashboard summary rows in `gateway_sessions` and
`axle_records`.

## RDSO/TMS Mapping

The RDSO paragraph covering intermediate-server storage and TMS hand-off maps
to this implementation as follows:

- "database or ASCII file": SQLite locally and PostgreSQL in cloud, with open
  ASCII/CSV export files for the two required hand-off datasets.
- "spatial acceleration data": parsed from `rms/rms_25cm.bin` into
  `rms_records`, then exported as `spatial_acceleration_export.csv`.
- "processed data having peaks": parsed from `peak/peak_50m.bin` into
  `peak_records`, then exported as `processed_peak_export.csv`.
- "preferably MDB": export includes a target MDB container when the runtime can
  create it; the open ASCII/CSV files remain the authoritative populated data
  on Linux because Access/Jet write support is Windows-only.
- "MMD envelope": this is not a cloud/TMS data file and not a CSV export. It is
  a hardware/mechanical mounting compliance requirement against the IR Schedule
  of Dimension. Store drawings/sign-off as project evidence if required, but
  the cloud cannot prove physical MMD clearance from acceleration data.
- "route-wise limits editable by purchaser": implemented in Threshold Settings
  and stored in `threshold_settings`.
- "alerts containing value and GPS location": implemented in `alerts`, derived
  from uploaded session GPS/peak data and shown on the Alerts map.
- "SMS/notification alerts": implemented as an auditable outbox. Configure
  `ALERT_NOTIFICATION_WEBHOOK_URL` to push each alert to an SMS/notification
  provider.
- "transfer to CRIS server": implemented as a TMS delivery service. Default
  local mode writes the ZIP to disk for hand-off; configure
  `TMS_DELIVERY_MODE=http` and `TMS_HTTP_URL` when CRIS provides the receiving
  endpoint.
