from __future__ import annotations

import json
import time

try:
    import pika
except ImportError:
    pika = None

from shared.config import QUEUE_NAME, RABBITMQ_URL


def _connection_parameters() -> pika.URLParameters:
    if pika is None:
        raise RuntimeError("pika is required for queue publishing")
    return pika.URLParameters(RABBITMQ_URL)


def _declare_queue(channel) -> None:
    channel.queue_declare(queue=QUEUE_NAME, durable=True)


def publish_job(job_payload: dict, retry_attempts: int = 3, retry_backoff_seconds: int = 2) -> None:
    if "data_id" not in job_payload:
        raise ValueError("Job payload must include data_id")

    has_legacy_values = "values" in job_payload
    has_node_metrics = (
        "node_id" in job_payload
        and "metrics" in job_payload
    )
    if not has_legacy_values and not has_node_metrics:
        raise ValueError("Job payload must include values or node metrics")

    body = json.dumps(job_payload)
    last_error = None

    for attempt in range(1, retry_attempts + 1):
        connection = None
        try:
            if pika is None:
                raise RuntimeError("pika is required for queue publishing")
            connection = pika.BlockingConnection(_connection_parameters())
            channel = connection.channel()
            _declare_queue(channel)
            channel.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )
            return
        except Exception as exc:
            last_error = exc
            if attempt < retry_attempts:
                time.sleep(retry_backoff_seconds)
        finally:
            if connection and connection.is_open:
                connection.close()

    raise RuntimeError(f"Failed to publish queue job after {retry_attempts} attempts: {last_error}")