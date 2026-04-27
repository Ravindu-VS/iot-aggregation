from __future__ import annotations

import uuid
from statistics import mean

from db.database import (
    get_record,
    insert_record,
    list_records,
    update_record_status,
    update_record_summary,
)

from backend.exceptions import BackendError, RecordNotFoundError, ValidationError
from backend.models import SensorSummary, generate_object_key
from backend.validators import normalize_sensor_payload, validate_sensor_payload
from shared.storage import store_raw_payload


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_sensor_payload(payload: dict) -> dict:
    """Ingest sensor payload with node_id, store raw data to MinIO, and return record."""
    
    # Step 1 – validate
    validate_sensor_payload(payload)

    # Step 2 – normalize
    normalized = normalize_sensor_payload(payload)
    sensor_id: str = normalized.sensor_id
    node_id: str = normalized.node_id
    metrics: dict = normalized.metrics

    # Step 3 – generate identifiers
    data_id: str = str(uuid.uuid4())
    object_key: str = generate_object_key(sensor_id, data_id)

    # Step 4 – store raw payload to MinIO
    try:
        store_raw_payload(object_key, payload)
    except Exception as exc:
        raise BackendError(f"Failed to store raw payload: {exc}") from exc

    # Step 5 – persist record with node_id and metrics
    try:
        insert_record(
            data_id=data_id,
            sensor_id=sensor_id,
            node_id=node_id,
            object_key=object_key,
            metrics=metrics,
        )
    except Exception as exc:
        raise BackendError(f"Failed to insert record: {exc}") from exc

    # Step 6 – fetch the newly created record
    try:
        record = get_record(data_id)
    except Exception as exc:
        raise BackendError(f"Failed to retrieve record after insert: {exc}") from exc

    if record is None:
        raise BackendError(
            f"Record {data_id} not found after insert — possible data consistency issue"
        )

    return record


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def list_uploads() -> list[dict]:
    try:
        return list_records()
    except Exception as exc:
        raise BackendError(f"Failed to list records: {exc}") from exc


# ---------------------------------------------------------------------------
# Summary retrieval
# ---------------------------------------------------------------------------

def get_summary_by_id(data_id: str) -> dict:
    try:
        record = get_record(data_id)
    except Exception as exc:
        raise BackendError(f"Failed to retrieve record: {exc}") from exc

    if record is None:
        raise RecordNotFoundError(data_id)

    return record


# ---------------------------------------------------------------------------
# Worker helpers — status transitions
# ---------------------------------------------------------------------------

def mark_processing(data_id: str) -> dict:
    _ensure_record_exists(data_id)

    try:
        update_record_status(data_id, "processing")
    except Exception as exc:
        raise BackendError(f"Failed to mark record as processing: {exc}") from exc

    try:
        record = get_record(data_id)
    except Exception as exc:
        raise BackendError(
            f"Failed to retrieve record after marking processing: {exc}"
        ) from exc

    if record is None:
        raise BackendError(
            f"Record {data_id} not found after marking processing"
        )

    return record


def mark_completed(data_id: str, summary: dict) -> dict:
    _ensure_record_exists(data_id)

    try:
        update_record_summary(data_id, summary)
    except Exception as exc:
        raise BackendError(f"Failed to mark record as completed: {exc}") from exc

    try:
        record = get_record(data_id)
    except Exception as exc:
        raise BackendError(
            f"Failed to retrieve record after marking completed: {exc}"
        ) from exc

    if record is None:
        raise BackendError(
            f"Record {data_id} not found after marking completed"
        )

    return record


def mark_failed(data_id: str) -> dict:
    _ensure_record_exists(data_id)

    try:
        update_record_status(data_id, "failed")
    except Exception as exc:
        raise BackendError(f"Failed to mark record as failed: {exc}") from exc

    try:
        record = get_record(data_id)
    except Exception as exc:
        raise BackendError(
            f"Failed to retrieve record after marking failed: {exc}"
        ) from exc

    if record is None:
        raise BackendError(
            f"Record {data_id} not found after marking failed"
        )

    return record


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def compute_summary(values: list[float]) -> dict:
    if not isinstance(values, list) or len(values) == 0:
        raise ValidationError("compute_summary requires a non-empty list of values")

    summary = SensorSummary(
        min_value=min(values),
        max_value=max(values),
        avg_value=round(mean(values), 4),
        count=len(values),
    )
    return summary.to_dict()


def compute_metrics_summary(metrics: dict[str, float], node_id: str) -> dict:
    """
    Compute per-metric summaries from a metrics dictionary.
    
    Args:
        metrics: Dictionary of {metric_name: value}
        node_id: Node identifier for the metrics
    
    Returns:
        Dictionary of {metric_name: {latest, count}} for single-reading payloads.
        Legacy records may still include min/max/avg from older data.
    """
    if not isinstance(metrics, dict) or len(metrics) == 0:
        return {}
    
    summary = {}
    for metric_name, value in metrics.items():
        if isinstance(value, (int, float)):
            summary[metric_name] = {
                "node_id": node_id,
                "latest": float(value),
                "count": 1,
            }
    
    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_record_exists(data_id: str) -> dict:
    try:
        record = get_record(data_id)
    except Exception as exc:
        raise BackendError(f"Failed to look up record: {exc}") from exc

    if record is None:
        raise RecordNotFoundError(data_id)

    return record
