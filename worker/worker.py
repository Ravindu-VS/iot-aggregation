from __future__ import annotations

import json
import logging
import sys
import time

# Ensure project root modules are importable when running as /app/worker/worker.py.
sys.path.insert(0, "/app")

try:
    import pika
    from pika.exceptions import AMQPConnectionError
except ImportError:
    pika = None

    class AMQPConnectionError(Exception):
        pass

from backend.exceptions import BackendError, RecordNotFoundError, ValidationError
from backend.services import compute_summary, compute_metrics_summary, mark_completed, mark_failed, mark_processing
from db.alerts import (
    create_alert_states_table_if_not_exists,
    create_alerts_table_if_not_exists,
    get_alert_state,
    upsert_alert,
    upsert_alert_state,
)
from db.database import create_table_if_not_exists
from shared.config import MAX_JOB_RETRIES, QUEUE_NAME, RABBITMQ_URL, RETRY_BACKOFF_SECONDS
from shared.queue import publish_job
from shared.storage import fetch_raw_payload


logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ALERT_THRESHOLDS = {
    "temperature": {"type": "high", "value": 40.0, "unit": "°C", "label": "Temperature"},
    "humidity": {"type": "high", "value": 80.0, "unit": "%", "label": "Humidity"},
    "pressure": {"type": "range", "min": 980.0, "max": 1030.0, "unit": "hPa", "label": "Pressure"},
    "ethanol": {"type": "high", "value": 30.0, "unit": "ppm", "label": "Ethanol"},
}


def parse_job_message(body: bytes) -> dict:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise ValidationError(f"Invalid job payload format: {exc}") from exc

    data_id = payload.get("data_id")

    if not isinstance(data_id, str) or not data_id.strip():
        raise ValidationError("Job payload missing valid data_id")
    
    # Node-based metrics processing: object_key and node_id are present
    if "object_key" in payload and "node_id" in payload:
        return {
            "data_id": data_id,
            "sensor_id": payload.get("sensor_id"),
            "node_id": payload.get("node_id"),
            "object_key": payload.get("object_key"),
            "metrics": payload.get("metrics", {}),
            "retry_count": int(payload.get("retry_count", 0)),
            "is_metrics_job": True,
        }
    
    # Legacy values-based processing
    values = payload.get("values", [])
    if not isinstance(values, list) or len(values) == 0:
        raise ValidationError("Job payload missing non-empty values list or object_key")
    if any(not isinstance(v, (int, float)) for v in values):
        raise ValidationError("All job values must be numeric")

    return {
        "data_id": data_id,
        "sensor_id": payload.get("sensor_id"),
        "values": [float(v) for v in values],
        "retry_count": int(payload.get("retry_count", 0)),
        "is_metrics_job": False,
    }


def process_job(payload: dict) -> dict:
    data_id = payload["data_id"]
    is_metrics_job = payload.get("is_metrics_job", False)
    
    mark_processing(data_id)
    
    if is_metrics_job:
        # New metrics-based job processing
        node_id = payload["node_id"]
        object_key = payload.get("object_key")
        metrics = payload.get("metrics", {})
        
        # If object_key is present, fetch raw data from MinIO
        if object_key:
            raw_payload = fetch_raw_payload(object_key)
            if isinstance(raw_payload, dict):
                metrics = raw_payload.get("metrics", metrics)
        
        summary = compute_metrics_summary(metrics, node_id)

        for event in _build_alert_events(payload, summary):
            upsert_alert(event)
    else:
        # Legacy values-based job processing
        values = payload["values"]
        summary = compute_summary(values)
    
    return mark_completed(data_id, summary)


def _build_alert_events(payload: dict, summary: dict) -> list[dict]:
    data_id = payload.get("data_id")
    node_id = payload.get("node_id")
    sensor_id = payload.get("sensor_id")
    events = []

    if not isinstance(summary, dict):
        return events

    for metric_name, metric_summary in summary.items():
        if not isinstance(metric_summary, dict):
            continue
        value = metric_summary.get("latest")
        if not isinstance(value, (int, float)):
            continue

        threshold = ALERT_THRESHOLDS.get(metric_name)
        if not threshold:
            continue

        state_id = f"{sensor_id}:{metric_name}"
        alert_state = get_alert_state(state_id)

        message = _evaluate_threshold_message(threshold, float(value))
        if not message:
            if alert_state and alert_state.get("status") == "breached":
                upsert_alert_state({"state_id": state_id, "status": "normal", "sensor_id": sensor_id, "metric": metric_name})
            continue

        # Avoid duplicate alerts while the metric is already in breached state.
        if alert_state and alert_state.get("status") == "breached":
            continue

        alert_id = f"{data_id}:{metric_name}"
        events.append(
            {
                "alert_id": alert_id,
                "data_id": data_id,
                "node_id": node_id,
                "sensor_id": sensor_id,
                "metric": metric_name,
                "value": float(value),
                "threshold": threshold,
                "message": message,
                "status": "active",
            }
        )
        upsert_alert_state({"state_id": state_id, "status": "breached", "sensor_id": sensor_id, "metric": metric_name, "alert_id": alert_id})

    return events


def _evaluate_threshold_message(threshold: dict, value: float) -> str | None:
    ttype = threshold.get("type")
    if ttype == "high" and value > float(threshold["value"]):
        return f"exceeded threshold ({threshold['value']} {threshold['unit']})"
    if ttype == "low" and value < float(threshold["value"]):
        return f"dropped below threshold ({threshold['value']} {threshold['unit']})"
    if ttype == "range" and (value < float(threshold["min"]) or value > float(threshold["max"])):
        return f"outside range ({threshold['min']}-{threshold['max']} {threshold['unit']})"
    return None


def handle_job_failure(payload: dict, error: Exception) -> str:
    data_id = payload.get("data_id", "")
    retry_count = int(payload.get("retry_count", 0))

    if retry_count < MAX_JOB_RETRIES:
        retry_payload = dict(payload)
        retry_payload["retry_count"] = retry_count + 1
        retry_payload["last_error"] = str(error)
        publish_job(retry_payload)
        logger.warning(
            "Job %s failed; requeued attempt %s/%s",
            data_id,
            retry_payload["retry_count"],
            MAX_JOB_RETRIES,
        )
        return "retried"

    if isinstance(data_id, str) and data_id.strip():
        try:
            mark_failed(data_id)
        except BackendError as exc:
            logger.error("Failed to mark %s as failed: %s", data_id, exc)

    logger.error("Job %s exhausted retries and is marked failed", data_id)
    return "failed"


def on_message(channel, method, properties, body: bytes) -> None:
    payload = None
    try:
        payload = parse_job_message(body)
        process_job(payload)
        logger.info("Job %s processed successfully", payload["data_id"])
    except (ValidationError, RecordNotFoundError) as exc:
        logger.error("Dropping invalid/unresolvable job: %s", exc)
    except Exception as exc:
        logger.exception("Unexpected worker error while processing message")
        try:
            if payload is None:
                payload = parse_job_message(body)
            handle_job_failure(payload, exc)
        except Exception as inner_exc:
            logger.error("Failed to handle job error path: %s", inner_exc)
    finally:
        channel.basic_ack(delivery_tag=method.delivery_tag)


def _build_connection() -> pika.BlockingConnection:
    if pika is None:
        raise RuntimeError("pika is required for worker queue consumption")
    params = pika.URLParameters(RABBITMQ_URL)
    return pika.BlockingConnection(params)


def start_worker_loop() -> None:
    create_table_if_not_exists()
    create_alerts_table_if_not_exists()
    create_alert_states_table_if_not_exists()

    while True:
        connection = None
        try:
            connection = _build_connection()
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=on_message)
            logger.info("Worker consuming queue: %s", QUEUE_NAME)
            channel.start_consuming()
        except AMQPConnectionError as exc:
            logger.warning("RabbitMQ unavailable, retrying in %ss: %s", RETRY_BACKOFF_SECONDS, exc)
            time.sleep(RETRY_BACKOFF_SECONDS)
        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            break
        finally:
            if connection and connection.is_open:
                connection.close()


if __name__ == "__main__":
    start_worker_loop()
