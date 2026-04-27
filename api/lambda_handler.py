from __future__ import annotations

import base64
import json
import logging
from typing import Any
from urllib.parse import unquote

from backend.exceptions import BackendError, RecordNotFoundError, ValidationError
from backend.services import get_summary_by_id, ingest_sensor_payload, list_uploads
from db.alerts import clear_alert, create_alert_states_table_if_not_exists, create_alerts_table_if_not_exists, list_alerts
from db.database import create_table_if_not_exists
from shared.queue import publish_job

logger = logging.getLogger(__name__)

_db_initialized = False


def _json_response(status_code: int, payload: Any) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        },
        "body": json.dumps(payload),
        "isBase64Encoded": False,
    }


def _ensure_db_initialized() -> None:
    global _db_initialized
    if _db_initialized:
        return

    try:
        create_table_if_not_exists()
        create_alerts_table_if_not_exists()
        create_alert_states_table_if_not_exists()
        _db_initialized = True
    except Exception as exc:
        logger.warning("Database initialization skipped or failed: %s", exc)


def _decode_body(event: dict) -> dict:
    body = event.get("body")
    if not body:
        return {}

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    if isinstance(body, bytes):
        body = body.decode("utf-8")

    return json.loads(body)


def handler(event, context):
    _ensure_db_initialized()

    method = (event.get("httpMethod") or "GET").upper()
    path = event.get("path") or "/"
    query = event.get("queryStringParameters") or {}

    if method == "OPTIONS":
        return _json_response(204, "")

    try:
        if path == "/health" and method == "GET":
            return _json_response(200, {"status": "ok"})

        if path == "/data" and method == "POST":
            body = _decode_body(event)
            record = ingest_sensor_payload(body)

            publish_job(
                {
                    "data_id": record["data_id"],
                    "sensor_id": record.get("sensor_id"),
                    "node_id": record.get("node_id"),
                    "object_key": record.get("object_key"),
                    "metrics": record.get("metrics", {}),
                    "retry_count": 0,
                }
            )

            return _json_response(202, {"data_id": record["data_id"], "status": record.get("status", "pending")})

        if path == "/summary" and method == "GET":
            data_id = query.get("id")
            if not data_id:
                return _json_response(400, {"error": "id is required"})
            return _json_response(200, get_summary_by_id(data_id))

        if path == "/list" and method == "GET":
            return _json_response(200, {"data": list_uploads()})

        if path == "/alerts" and method == "GET":
            return _json_response(200, {"data": list_alerts(active_only=True)})

        if path.startswith("/alerts/") and method == "DELETE":
            alert_id = unquote(path.split("/", 2)[2])
            if not alert_id:
                return _json_response(400, {"error": "alert_id is required"})
            cleared = clear_alert(alert_id)
            if not cleared:
                return _json_response(404, {"error": "not found"})
            return _json_response(200, {"status": "cleared", "alert_id": alert_id})

        return _json_response(404, {"error": "endpoint not found"})

    except ValidationError as exc:
        return _json_response(400, {"error": str(exc)})
    except RecordNotFoundError:
        return _json_response(404, {"error": "not found"})
    except BackendError as exc:
        return _json_response(500, {"error": str(exc)})
    except Exception as exc:
        logger.exception("Unhandled API error")
        return _json_response(500, {"error": f"internal server error: {exc}"})