import hashlib
import io
import json
import re
import shutil
import struct
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.services.alerts import evaluate_alerts, get_or_default_threshold

REQUIRED_FILES = [
    "session_metadata.json",
    "rms/rms_25cm.bin",
    "peak/peak_50m.bin",
    "faults/faults.bin",
    "raw/adxl_left.bin",
    "raw/adxl_right.bin",
    "raw/bogie.bin",
    "raw/encoder.bin",
]

RMS_RECORD_SIZE = 66
PEAK_RECORD_SIZE = 302
FAULT_RECORD_SIZE = 75
SENTINEL_U32 = 0xFFFFFFFF
AXIS_NAMES = ["al_x", "al_y", "al_z", "ar_x", "ar_y", "ar_z", "bg_x", "bg_y", "bg_z"]
ARCHIVE_NAME_RE = re.compile(r"^(?P<gateway>.+)__(?P<train>.+?)__(?P<session>SESSION_\d{8}_\d{6})\.zip$")


def looks_like_gateway_zip(raw: bytes) -> bool:
    return raw.startswith(b"PK\x03\x04") or raw.startswith(b"PK\x05\x06") or raw.startswith(b"PK\x07\x08")


def archive_name_from_headers(headers) -> Optional[str]:
    direct = headers.get("x-archive-name") or headers.get("x-filename")
    if direct:
        return Path(direct).name

    content_disposition = headers.get("content-disposition", "")
    match = re.search(r'filename="?([^";]+)"?', content_disposition)
    if match:
        return Path(match.group(1)).name
    return None


def _parse_created_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _zip_member_map(zf: zipfile.ZipFile) -> Dict[str, str]:
    names = [name for name in zf.namelist() if not name.endswith("/")]
    mapped: Dict[str, str] = {}
    for required in REQUIRED_FILES:
        for name in names:
            normalized = name.replace("\\", "/").lstrip("/")
            if normalized == required or normalized.endswith(f"/{required}"):
                mapped[required] = name
                break
    return mapped


def _read_required_json(zf: zipfile.ZipFile, members: Dict[str, str]) -> dict:
    metadata_member = members.get("session_metadata.json")
    if not metadata_member:
        raise HTTPException(status_code=422, detail="Gateway ZIP missing session_metadata.json")
    try:
        return json.loads(zf.read(metadata_member).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid session_metadata.json: {exc}")


def _validate_metadata(metadata: dict) -> None:
    required = [
        "schemaVersion", "gatewayId", "gatewaySerial", "trainId", "firmwareVersion",
        "gatewaySoftware", "sessionName", "sessionStatus", "createdUtc",
    ]
    missing = [field for field in required if field not in metadata]
    if missing:
        raise HTTPException(status_code=422, detail=f"session_metadata.json missing fields: {missing}")
    if metadata["schemaVersion"] != "1.0":
        raise HTTPException(status_code=422, detail=f"Unsupported schemaVersion: {metadata['schemaVersion']}")
    if metadata["sessionStatus"] not in {"active", "closed"}:
        raise HTTPException(status_code=422, detail=f"Invalid sessionStatus: {metadata['sessionStatus']}")


def _validate_filename(archive_name: Optional[str], metadata: dict) -> str:
    expected = f"{metadata['gatewayId']}__{metadata['trainId']}__{metadata['sessionName']}.zip"
    if not archive_name:
        return expected

    match = ARCHIVE_NAME_RE.match(archive_name)
    if not match:
        raise HTTPException(status_code=422, detail=f"Invalid archive filename: {archive_name}")

    mismatches = []
    if match.group("gateway") != metadata["gatewayId"]:
        mismatches.append("gatewayId")
    if match.group("train") != metadata["trainId"]:
        mismatches.append("trainId")
    if match.group("session") != metadata["sessionName"]:
        mismatches.append("sessionName")
    if mismatches:
        raise HTTPException(status_code=422, detail=f"Archive filename metadata mismatch: {mismatches}")
    return archive_name


def _storage_root(gateway_id: str, session_name: str) -> Path:
    root = Path(settings.ARCHIVE_STORAGE_DIR) / gateway_id / session_name
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(data)


def _store_files(
    zf: zipfile.ZipFile,
    members: Dict[str, str],
    archive_id: int,
    session_id: Optional[int],
    root: Path,
    db: Session,
) -> None:
    record_sizes = {
        "rms/rms_25cm.bin": RMS_RECORD_SIZE,
        "peak/peak_50m.bin": PEAK_RECORD_SIZE,
        "faults/faults.bin": FAULT_RECORD_SIZE,
    }
    for relative_path, member_name in members.items():
        data = zf.read(member_name)
        destination = root / "extracted" / relative_path
        _write_bytes(destination, data)
        record_size = record_sizes.get(relative_path)
        integrity_ok = True if record_size is None else len(data) % record_size == 0
        db.add(models.ExtractedFile(
            archive_id=archive_id,
            session_id=session_id,
            file_relative_path=relative_path,
            file_size_bytes=len(data),
            storage_uri=str(destination),
            integrity_ok=integrity_ok,
        ))


def _chunks(data: bytes, size: int) -> Iterable[bytes]:
    for offset in range(0, len(data) - (len(data) % size), size):
        yield data[offset:offset + size]


def _parse_rms_records(data: bytes, archive_id: int, session_id: int, db: Session) -> list[models.RmsRecord]:
    records = []
    fmt = struct.Struct("<QiddBB9I")
    for raw in _chunks(data, RMS_RECORD_SIZE):
        values = fmt.unpack(raw)
        rec = models.RmsRecord(
            archive_id=archive_id,
            session_id=session_id,
            master_count=values[0],
            position_mm=values[1],
            latitude=values[2],
            longitude=values[3],
            gps_valid=bool(values[4]),
            valid_mask=values[5],
            al_x_mg=values[6],
            al_y_mg=values[7],
            al_z_mg=values[8],
            ar_x_mg=values[9],
            ar_y_mg=values[10],
            ar_z_mg=values[11],
            bg_x_mg=values[12],
            bg_y_mg=values[13],
            bg_z_mg=values[14],
        )
        db.add(rec)
        records.append(rec)
    return records


def _parse_axis(raw: bytes, base: int) -> dict:
    peak_value_mg, peak_position_mm, peak_master_count, peak_lat, peak_lon = struct.unpack_from("<IiQdd", raw, base)
    return {
        "peakValueMg": peak_value_mg,
        "peakPositionMm": peak_position_mm,
        "peakMasterCount": peak_master_count,
        "peakLat": peak_lat,
        "peakLon": peak_lon,
    }


def _parse_peak_records(data: bytes, archive_id: int, session_id: int, db: Session) -> list[models.PeakRecord]:
    records = []
    header = struct.Struct("<iifBB")
    axis_offsets = [14, 46, 78, 110, 142, 174, 206, 238, 270]
    for raw in _chunks(data, PEAK_RECORD_SIZE):
        window_start_mm, window_end_mm, speed_kmph, valid_mask, alert_generated = header.unpack_from(raw, 0)
        axes = {
            axis_name: _parse_axis(raw, offset)
            for axis_name, offset in zip(AXIS_NAMES, axis_offsets)
        }
        rec = models.PeakRecord(
            archive_id=archive_id,
            session_id=session_id,
            window_start_mm=window_start_mm,
            window_end_mm=window_end_mm,
            speed_kmph=speed_kmph,
            valid_mask=valid_mask,
            alert_generated=bool(alert_generated),
            axes=axes,
        )
        db.add(rec)
        records.append(rec)
    return records


def _parse_fault_records(data: bytes, archive_id: int, session_id: int, db: Session) -> int:
    fmt = struct.Struct("<QBBB64s")
    count = 0
    for raw in _chunks(data, FAULT_RECORD_SIZE):
        timestamp_ms, fault_code, node_id, severity, description_raw = fmt.unpack(raw)
        description = description_raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        db.add(models.FaultRecord(
            archive_id=archive_id,
            session_id=session_id,
            timestamp_ms=timestamp_ms,
            fault_code=fault_code,
            node_id=node_id,
            severity=severity,
            description=description,
        ))
        count += 1
    return count


def _mg_to_g(value: int) -> float:
    if value in (0, SENTINEL_U32):
        return 0.0
    return round(value / 1000.0, 4)


def _summary_axle_records(peaks: list[models.PeakRecord], session_id: int, db: Session) -> list[models.AxleRecord]:
    created = []
    node_axis = {
        "AL": ("al_y", "al_z"),
        "AR": ("ar_y", "ar_z"),
        "BG": ("bg_y", "bg_z"),
    }
    for peak in peaks:
        for axle_id, (lateral_axis, vertical_axis) in node_axis.items():
            lateral = _mg_to_g(peak.axes[lateral_axis]["peakValueMg"])
            vertical = _mg_to_g(peak.axes[vertical_axis]["peakValueMg"])
            peak_g = max(_mg_to_g(peak.axes[f"{axle_id.lower()}_{axis}"]["peakValueMg"]) for axis in ("x", "y", "z"))
            if peak_g <= 0:
                continue
            rec = models.AxleRecord(
                session_id=session_id,
                axle_id=axle_id,
                vertical_g=vertical,
                lateral_g=lateral,
                rms=max(vertical, lateral),
                peak=peak_g,
            )
            db.add(rec)
            created.append(rec)
    return created


def _best_location(rms_records: list[models.RmsRecord], peaks: list[models.PeakRecord]) -> tuple[float, float]:
    for rec in rms_records:
        if rec.gps_valid:
            return rec.latitude, rec.longitude
    for peak in peaks:
        for axis in peak.axes.values():
            lat, lon = axis["peakLat"], axis["peakLon"]
            if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0 or lon != 0):
                return lat, lon
    return 0.0, 0.0


def ingest_gateway_zip(
    raw: bytes,
    db: Session,
    archive_name: Optional[str] = None,
    route: Optional[str] = None,
) -> schemas.ArchiveResponse:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP archive")

    with zf:
        members = _zip_member_map(zf)
        metadata = _read_required_json(zf, members)
        _validate_metadata(metadata)
        archive_name = _validate_filename(archive_name, metadata)

        existing = (
            db.query(models.Archive)
            .filter_by(gateway_id=metadata["gatewayId"], session_name=metadata["sessionName"])
            .first()
        )
        if existing:
            return schemas.ArchiveResponse(
                status="success",
                archiveId=existing.id,
                alertsGenerated=0,
                message=f"Duplicate archive '{metadata['sessionName']}' already stored",
            )

        missing_files = [path for path in REQUIRED_FILES if path not in members]
        incomplete_sizes = []
        for path, record_size in {
            "rms/rms_25cm.bin": RMS_RECORD_SIZE,
            "peak/peak_50m.bin": PEAK_RECORD_SIZE,
            "faults/faults.bin": FAULT_RECORD_SIZE,
        }.items():
            if path in members and zf.getinfo(members[path]).file_size % record_size != 0:
                incomplete_sizes.append(path)

        validation_status = "ok"
        if missing_files or incomplete_sizes or metadata["sessionStatus"] != "closed":
            validation_status = "incomplete"

        checksum = hashlib.sha256(raw).hexdigest()
        root = _storage_root(metadata["gatewayId"], metadata["sessionName"])
        archive_path = root / archive_name
        _write_bytes(archive_path, raw)

        gateway = db.get(models.Gateway, metadata["gatewayId"])
        if gateway is None:
            gateway = models.Gateway(gateway_id=metadata["gatewayId"])
            db.add(gateway)
        gateway.status = "online"
        gateway.last_seen_at = datetime.utcnow()
        gateway.last_upload_at = datetime.utcnow()

        if db.get(models.Train, metadata["trainId"]) is None:
            db.add(models.Train(train_id=metadata["trainId"]))

        archive = models.Archive(
            gateway_id=metadata["gatewayId"],
            train_id=metadata["trainId"],
            session_name=metadata["sessionName"],
            archive_name=archive_name,
            archive_size_bytes=len(raw),
            storage_uri=str(archive_path),
            checksum=checksum,
            validation_status=validation_status,
            missing_files={"missing": missing_files, "badRecordSize": incomplete_sizes},
            metadata_json=metadata,
        )
        db.add(archive)
        db.flush()

        session = models.GatewaySession(
            session_id=metadata["sessionName"],
            gateway_id=metadata["gatewayId"],
            train_id=metadata["trainId"],
            route=route or "Bangalore-Chennai",
            timestamp=_parse_created_utc(metadata["createdUtc"]),
            lat=0.0,
            lon=0.0,
            speed_kmph=0.0,
            raw_payload=metadata,
        )
        db.add(session)
        db.flush()

        _store_files(zf, members, archive.id, session.id, root, db)

        rms_records = []
        if "rms/rms_25cm.bin" in members:
            rms_records = _parse_rms_records(zf.read(members["rms/rms_25cm.bin"]), archive.id, session.id, db)

        peak_records = []
        if "peak/peak_50m.bin" in members:
            peak_records = _parse_peak_records(zf.read(members["peak/peak_50m.bin"]), archive.id, session.id, db)

        if "faults/faults.bin" in members:
            _parse_fault_records(zf.read(members["faults/faults.bin"]), archive.id, session.id, db)

        session.lat, session.lon = _best_location(rms_records, peak_records)
        session.speed_kmph = max((p.speed_kmph for p in peak_records), default=0.0)

        axle_records = _summary_axle_records(peak_records, session.id, db)
        db.flush()

        alerts_created = evaluate_alerts(
            session,
            axle_records,
            get_or_default_threshold(db, session.route),
            db,
        )
        db.commit()

        return schemas.ArchiveResponse(
            status="success",
            archiveId=archive.id,
            alertsGenerated=len(alerts_created),
            message=(
                f"Gateway ZIP '{metadata['sessionName']}' stored: "
                f"{len(rms_records)} RMS, {len(peak_records)} peak, {len(axle_records)} summary reading(s)"
            ),
        )
