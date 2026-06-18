# UABAMS Cloud Project Workflow and Status

## 1. Current Running URLs

- Dashboard: `http://127.0.0.1:5174`
- Backend API docs: `http://127.0.0.1:8001/docs`
- TMS export API: `http://127.0.0.1:8001/api/v1/export/tms`

## 2. High-Level Workflow

```text
Gateway / Simulator
  -> uploads data to backend /api/v1/archive
  -> backend validates and parses the upload
  -> backend stores data in database and archive storage
  -> dashboard reads backend APIs
  -> operator views sessions, alerts, map, charts, thresholds, calibration
  -> TMS export creates CRIS/TMS hand-off ZIP
```

## 3. Data Upload Modes

### Demo Upload

The dashboard Gateway Upload page sends a simple JSON payload to:

```text
POST /api/v1/archive
```

This creates dashboard data in:

- `gateway_sessions`
- `axle_records`
- `alerts`
- `gateways`

### Real Gateway ZIP Upload

The backend also supports the ICD gateway ZIP format:

```text
PUT /api/v1/archive

session_metadata.json
rms/rms_25cm.bin
peak/peak_50m.bin
faults/faults.bin
raw/adxl_left.bin
raw/adxl_right.bin
raw/bogie.bin
raw/encoder.bin
```

For strict filename validation, the gateway should send:

```text
X-Archive-Name: GW_BOGIE_001__TRAIN_07__SESSION_20260609_083015.zip
```

Real ZIP data is stored in:

- `archives`
- `extracted_files`
- `rms_records`
- `peak_records`
- `fault_records`

The backend also creates dashboard summary rows so the uploaded session appears in the UI.

## 4. Database Location

Local SQLite database:

```text
C:\Users\Pilabs\AppData\Local\Temp\uabams-cloud\uabams.db
```

Open it with DB Browser for SQLite and use the Browse Data tab.

## 5. Archive Storage Location

Original gateway ZIP files and extracted binary files are preserved under:

```text
C:\Users\Pilabs\AppData\Local\Temp\uabams-cloud\archives
```

These files are permanent audit artifacts according to the ICD.

## 6. Current Local Database Status

Checked on 18 June 2026:

| Table | Rows | Meaning |
|---|---:|---|
| `alerts` | 44 | Demo/generated alert records |
| `gateway_sessions` | 97 | Uploaded/demo session summaries |
| `axle_records` | 198 | Dashboard RMS/peak summary rows |
| `threshold_settings` | 3 | Route-wise thresholds |
| `calibration` | 26 | Wheel calibration records |
| `gateways` | 4 | Gateway status rows |
| `trains` | 5 | Train roster |
| `route_track_points` | 48 | Route/KM reference points |
| `archives` | 0 | No real ICD ZIP uploaded yet |
| `extracted_files` | 0 | No real ICD ZIP uploaded yet |
| `rms_records` | 0 | Filled only by real `rms_25cm.bin` uploads |
| `peak_records` | 0 | Filled only by real `peak_50m.bin` uploads |
| `fault_records` | 0 | Filled only by real `faults.bin` uploads |

## 7. Dashboard Pages

- Dashboard: summary cards, RMS/peak charts, route violations, GPS positions, recent sessions, TMS export.
- Gateway Upload: sends a demo upload to test ingestion.
- Threshold Settings: route-wise vertical/lateral limits.
- Calibration: wheel diameter, wear percentage, correction factor history.
- Alerts: alert table, severity cards, GPS alert map, route chart, trend graph.

## 8. TMS Export

The export button creates:

```text
spatial_acceleration_export.csv
processed_peak_export.csv
README_MDB_EXPORT.txt
uabams_tms_target.mdb (when runtime can create it)
```

Current generated export file:

```text
C:\Users\Pilabs\OneDrive\Desktop\Uabams\uabams-cloud\exports\uabams_tms_export_30d.zip
```

The export uses:

- `rms_records` and `peak_records` when real ICD ZIP data exists.
- Dashboard summary rows as fallback for demo data.

## 9. RDSO/ICD Requirement Mapping

| Requirement | Project Status |
|---|---|
| Data stored in database or ASCII file | Implemented: SQLite/PostgreSQL plus CSV export |
| Spatial acceleration data | Implemented for real ZIP: `rms_records` from `rms_25cm.bin` |
| Processed peak data | Implemented for real ZIP: `peak_records` from `peak_50m.bin` |
| Alerts with value and GPS location | Implemented in `alerts` and Alerts map |
| Route-wise editable thresholds | Implemented in Threshold Settings |
| TMS hand-off | Implemented as export ZIP with CSV files and optional MDB |
| Original ZIP permanent retention | Implemented via archive storage path |
| Raw binary extracted-file retention | Implemented via `extracted_files` and archive folder |
| Real-time SMS/notification sending | Not implemented; dashboard/backend alerts only |
| Hardware/MMD compliance | Not part of cloud software; hardware/vendor responsibility |
| Encryption/private APN/GSM network | Not implemented in local demo; deployment/network responsibility |

## 10. Server Deployment Status

The project does not automatically go to a public server just by running locally.

Current status:

- Local dashboard runs on the laptop.
- GitHub repository is pushed.
- Render deployment config exists in `render.yaml`.

To put it on a real server:

1. Push latest code to GitHub.
2. Create a Render Blueprint from the GitHub repository.
3. Render creates the backend service, frontend static site, and PostgreSQL database.
4. Set frontend `VITE_API_BASE_URL` to the live backend URL.
5. Configure gateway devices to upload to:

```text
https://<backend-service-url>/api/v1/archive
```

For production, SQLite should be replaced by PostgreSQL using `DATABASE_URL`.

## 11. Confirmation

The local project is working for dashboard/demo flow and has backend support for real ICD ZIP ingestion. The current database screenshot shows demo data in `alerts`, which is expected. The real ICD data tables are present but empty until an actual gateway ZIP archive is uploaded.
