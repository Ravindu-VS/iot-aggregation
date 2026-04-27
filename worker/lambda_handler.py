import json
import logging
from typing import Any

from backend.exceptions import BackendError, RecordNotFoundError, ValidationError
from worker.worker import handle_job_failure, parse_job_message, process_job

logger = logging.getLogger("worker_lambda")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _to_bytes(body: Any) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body).encode("utf-8")


def handler(event, context):
    records = event.get("Records", [])
    if not isinstance(records, list):
        logger.error("Unexpected event format: missing Records list")
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid event format"})}

    for record in records:
        body = record.get("body")
        if body is None:
            logger.error("Skipping record without body: %s", record)
            continue

        payload = None
        try:
            payload = parse_job_message(_to_bytes(body))
            process_job(payload)
            logger.info("Processed job %s successfully", payload.get("data_id"))
        except (ValidationError, RecordNotFoundError) as exc:
            logger.error("Dropping invalid/unresolvable job: %s", exc)
        except Exception as exc:
            logger.exception("Unexpected worker error while processing message")
            try:
                if payload is None:
                    payload = parse_job_message(_to_bytes(body))
                handle_job_failure(payload, exc)
            except Exception as inner_exc:
                logger.exception("Failed to handle job failure for message: %s", inner_exc)

    return {"statusCode": 200, "body": json.dumps({"processed": len(records)})}
