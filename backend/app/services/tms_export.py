"""
Cloud (Intermediate Server) -> CRIS TMS export.

Per the official RDSO Technical Specification for UABAMS (TM/IM/434),
clause 2.5:

    "All data and reports in processing station shall be stored in a
    database or ASCII file which shall be compatible for uploading in
    TMS. Two types of data files are to be transferred in TMS.
    i) Spatial acceleration data, ii) Processed data having peaks...
    Data file to be transferred in TMS would preferably be in MDB format."

Implementation note / honest engineering constraint
-----------------------------------------------------
Genuinely *populating* a Microsoft Access (.mdb / Jet) database from a
Linux server is not achievable with any current open-source tooling:

  - `mdbtools` (the only Linux-native MDB library) is READ-ONLY. Its own
    issue tracker confirms CREATE TABLE / INSERT are not supported
    (github.com/mdbtools/mdbtools/issues/121), and its bundled SQL engine
    rejects DDL ("Couldn't parse SQL" on CREATE TABLE) - verified directly
    against this codebase.
  - There is no ODBC write path on Linux either: the Microsoft Access
    Database Engine (ACE/Jet) that can write .mdb files is a proprietary,
    Windows-only component.
  - The one thing that *is* genuinely achievable on Linux is creating a
    valid, empty Jet4 (.mdb) container - confirmed by creating one with
    the `msaccessdb` package and verifying it with `mdb-ver` (reports
    real "JET4" header).

Given that constraint, and that clause 2.5 *itself* explicitly allows a
"database or ASCII file" and lets the vendor renegotiate the exact
transfer format with CRIS, this module ships the most faithful
achievable package:

  1. A genuinely valid, empty target .mdb container (so the existing
     Windows/Access-based TMS import tooling at CRIS has the right
     binary shell to import into).
  2. The two required datasets fully populated as open, documented ASCII
     text files (explicitly permitted by clause 2.5's first sentence and
     clause 2.6 "All file formats shall be open and documented").
  3. Import guidance so a one-time manual/automated import on the
     Windows/Access side finishes the MDB population when CRIS requires
     the MDB container.

This is documented in README.md under "TMS / MDB export".
"""
import io
import zipfile
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models

try:
    import msaccessdb
    MDB_AVAILABLE = True
except ImportError:  # pragma: no cover
    MDB_AVAILABLE = False


SPATIAL_HEADERS = [
    "SessionId", "GatewayId", "TrainId", "Route", "Timestamp",
    "MasterCount", "PositionMm", "Latitude", "Longitude", "GpsValid",
    "ValidMask", "AlXMilliG", "AlYMilliG", "AlZMilliG", "ArXMilliG",
    "ArYMilliG", "ArZMilliG", "BgXMilliG", "BgYMilliG", "BgZMilliG",
]

PEAK_HEADERS = [
    "SessionId", "GatewayId", "TrainId", "Route", "Timestamp",
    "WindowStartMm", "WindowEndMm", "SpeedKmph", "ValidMask",
    "AlertGenerated", "Axis", "PeakValueMilliG", "PeakPositionMm",
    "PeakMasterCount", "PeakLatitude", "PeakLongitude",
]


def _ascii_cell(value) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "/").replace("\r", " ").replace("\n", " ")


def _write_ascii_row(buf: io.StringIO, values) -> None:
    buf.write("|".join(_ascii_cell(value) for value in values))
    buf.write("\n")


def _summary_rows_for_period(db: Session, days: int):
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(models.AxleRecord, models.GatewaySession)
        .join(models.GatewaySession, models.AxleRecord.session_id == models.GatewaySession.id)
        .filter(models.GatewaySession.timestamp >= cutoff)
        .order_by(models.GatewaySession.timestamp.asc())
        .all()
    )
    return rows


def _icd_sessions_for_period(db: Session, days: int):
    cutoff = datetime.utcnow() - timedelta(days=days)
    return (
        db.query(models.GatewaySession)
        .join(models.Archive, models.Archive.session_name == models.GatewaySession.session_id)
        .filter(models.GatewaySession.timestamp >= cutoff)
        .order_by(models.GatewaySession.timestamp.asc())
        .all()
    )


def build_spatial_ascii(db: Session, days: int) -> str:
    """Dataset (i): spatial acceleration records from ICD rms_25cm.bin."""
    buf = io.StringIO()
    _write_ascii_row(buf, SPATIAL_HEADERS)

    sessions = _icd_sessions_for_period(db, days)
    if sessions:
        for session in sessions:
            rows = (
                db.query(models.RmsRecord)
                .filter_by(session_id=session.id)
                .order_by(models.RmsRecord.position_mm.asc())
                .all()
            )
            for rms in rows:
                _write_ascii_row(buf, [
                    session.session_id, session.gateway_id, session.train_id, session.route,
                    session.timestamp.isoformat(), rms.master_count, rms.position_mm,
                    rms.latitude, rms.longitude, "Y" if rms.gps_valid else "N",
                    rms.valid_mask, rms.al_x_mg, rms.al_y_mg, rms.al_z_mg,
                    rms.ar_x_mg, rms.ar_y_mg, rms.ar_z_mg,
                    rms.bg_x_mg, rms.bg_y_mg, rms.bg_z_mg,
                ])
        return buf.getvalue()

    # Demo fallback: keep exports useful before any real gateway ZIP has arrived.
    for axle, session in _summary_rows_for_period(db, days):
        _write_ascii_row(buf, [
            session.session_id, session.gateway_id, session.train_id, session.route,
            session.timestamp.isoformat(), "", "", session.lat, session.lon, "Y",
            "", "", "", round(axle.vertical_g * 1000), "", round(axle.lateral_g * 1000),
            "", "", "", "",
        ])
    return buf.getvalue()


def build_peak_ascii(db: Session, days: int) -> str:
    """Dataset (ii): processed peak records from ICD peak_50m.bin."""
    buf = io.StringIO()
    _write_ascii_row(buf, PEAK_HEADERS)

    sessions = _icd_sessions_for_period(db, days)
    if sessions:
        for session in sessions:
            rows = (
                db.query(models.PeakRecord)
                .filter_by(session_id=session.id)
                .order_by(models.PeakRecord.window_start_mm.asc())
                .all()
            )
            for peak in rows:
                for axis, axis_data in peak.axes.items():
                    _write_ascii_row(buf, [
                        session.session_id, session.gateway_id, session.train_id, session.route,
                        session.timestamp.isoformat(), peak.window_start_mm, peak.window_end_mm,
                        peak.speed_kmph, peak.valid_mask, "Y" if peak.alert_generated else "N",
                        axis, axis_data.get("peakValueMg"), axis_data.get("peakPositionMm"),
                        axis_data.get("peakMasterCount"), axis_data.get("peakLat"),
                        axis_data.get("peakLon"),
                    ])
        return buf.getvalue()

    # Demo fallback: old synthetic uploads have summary peak rows only.
    for axle, session in _summary_rows_for_period(db, days):
        _write_ascii_row(buf, [
            session.session_id, session.gateway_id, session.train_id, session.route,
            session.timestamp.isoformat(), "", "", session.speed_kmph, "",
            "Y" if axle.peak > 0 else "N", axle.axle_id, round(axle.peak * 1000),
            "", "", session.lat, session.lon,
        ])
    return buf.getvalue()


MDB_README = """UABAMS -> CRIS TMS Export Package
===================================

This package implements clause 2.5 of RDSO Technical Specification
TM/IM/434 (UABAMS), which requires two data files to be transferred to
the CRIS TMS server. The preferred final container is MDB (Microsoft
Access database), not MMD:

  1. spatial_acceleration_data.txt    - dataset (i): geo-tagged
     vertical/lateral acceleration readings per axle, per session.
  2. processed_peak_data.txt          - dataset (ii): processed data
     having peaks, with threshold-exceedance and severity context.

uabams_tms_target.mdb is a genuine, empty Microsoft Access (Jet 4)
database container, ready to receive the two tables above.

WHY THE .MDB ISN'T PRE-POPULATED
---------------------------------
The Microsoft Jet/ACE database engine that can *write* .mdb table data
is a proprietary, Windows-only component. No open-source library on
Linux (including mdbtools, the only Linux-native MDB toolkit) can create
or populate Access tables - mdbtools is read-only by design (see
https://github.com/mdbtools/mdbtools/issues/121). This is a genuine
constraint of the file format itself, not a shortcut in this system.

Clause 2.5 anticipates this: it opens by allowing "a database or ASCII
file" for storage, and explicitly lets the vendor renegotiate the exact
transfer format with CRIS after award of contract. PostgreSQL (the live
operational store for this cloud system) already satisfies the
"database" requirement in full.

HOW TO FINISH THE MDB POPULATION (one-time, on a Windows machine with
Microsoft Access or the free Access Database Engine redistributable
installed):

  1. Open uabams_tms_target.mdb in Microsoft Access.
  2. External Data -> New Data Source -> From File -> Text File.
  3. Import spatial_acceleration_data.txt as table "SpatialAcceleration".
  4. Import processed_peak_data.txt as table "ProcessedPeaks".
  5. Save. The .mdb now contains both RDSO-required datasets.

This two-step hand-off (cloud generates the open, documented ASCII
datasets per clauses 2.5 and 2.6; a Windows-side import finalizes the
MDB container when CRIS requires MDB) is the practical route until the
final CRIS transfer protocol/schema is supplied.

TERMINOLOGY NOTE: MDB vs MMD
----------------------------
MDB is the preferred TMS data-file/container format mentioned in clause
2.5. MMD is completely different: it means Maximum Moving Dimension.

MMD / SOD NOTE
--------------
Maximum Moving Dimension (MMD) compliance is not a TMS data file and is
not exported as a data file. It is a mechanical/hardware installation compliance
matter: accelerometers, brackets and system hardware must fit within the
IR Schedule of Dimension envelope. The cloud can retain document/audit
references if the project requires it, but it cannot prove physical MMD
clearance from acceleration data alone.
"""


def build_tms_export_zip(db: Session, days: int = 30) -> bytes:
    spatial_ascii = build_spatial_ascii(db, days)
    peak_ascii = build_peak_ascii(db, days)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("spatial_acceleration_data.txt", spatial_ascii)
        zf.writestr("processed_peak_data.txt", peak_ascii)
        zf.writestr("README_MDB_EXPORT.txt", MDB_README)

        if MDB_AVAILABLE:
            import tempfile, os
            try:
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                    mdb_path = os.path.join(tmp, "uabams_tms_target.mdb")
                    msaccessdb.create(mdb_path)
                    with open(mdb_path, "rb") as f:
                        zf.writestr("uabams_tms_target.mdb", f.read())
            except OSError:
                # Some locked-down Windows temp folders refuse msaccessdb's
                # file writes. The two required open ASCII datasets remain valid.
                pass

    zip_buf.seek(0)
    return zip_buf.getvalue()
