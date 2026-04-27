from flask import Flask, jsonify, request
import sys
import logging
from pathlib import Path

# Ensure project root modules (backend/, db/, shared/) are importable.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.exceptions import BackendError, RecordNotFoundError, ValidationError
from backend.services import (
    get_summary_by_id,
    ingest_sensor_payload,
    list_uploads as service_list_uploads,
    mark_failed,
)
from db.database import create_table_if_not_exists
from db.alerts import create_alerts_table_if_not_exists, list_alerts, clear_alert
from shared.queue import publish_job

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
    return response


@app.route("/", methods=["OPTIONS"])
@app.route("/<path:_path>", methods=["OPTIONS"])
def options_preflight(_path=None):
    return "", 204

# Defer database initialization to avoid connection errors during testing
# when the database service isn't running
_db_initialized = False

def _ensure_db_initialized():
    """Initialize database on first request if not already done."""
    global _db_initialized
    if not _db_initialized:
        try:
            create_table_if_not_exists()
            create_alerts_table_if_not_exists()
            _db_initialized = True
        except Exception as exc:
            logger.warning(f"Failed to initialize database: {exc}")
            # Continue anyway - tests don't need the actual database


def _with_db_recovery(operation_name: str, operation):
    """Run a DB-backed operation and retry once after table recovery if needed."""
    global _db_initialized

    try:
        return operation()
    except BackendError as exc:
        if "ResourceNotFoundException" not in str(exc):
            raise

        logger.warning(
            "%s failed due to missing table. Attempting table recovery.",
            operation_name,
        )

        try:
            create_table_if_not_exists()
            _db_initialized = True
        except Exception as init_exc:
            logger.error("Table recovery failed for %s: %s", operation_name, init_exc)
            raise

        return operation()


# ============================================================================
# Health & Status Endpoints
# ============================================================================


@app.route("/health", methods=["GET"])
def health():
    """
    Health check endpoint.
    
    Returns:
        200 OK with status "ok"
    """
    _ensure_db_initialized()
    return jsonify({"status": "ok"}), 200


# ============================================================================
# Data Ingestion Endpoints
# ============================================================================


@app.route("/data", methods=["POST"])
def receive_data():
    """
    Ingest sensor data for processing.
    
    This endpoint accepts sensor readings, validates them, stores the record,
    and queues a processing job. Processing happens asynchronously via the worker.
    
    Request JSON:
        {
            "sensor_id": "string (required, non-empty)",
            "values": [number...] (required, non-empty list)
        }
    
    Returns:
        202 Accepted: { "data_id": "uuid", "status": "pending" }
        400 Bad Request: { "error": "validation error message" }
        500 Internal Server Error: { "error": "server error message" }
    """
    # Parse and validate request
    body = request.get_json(silent=True) or {}
    
    # Log the request
    logger.info(f"Received POST /data with sensor_id={body.get('sensor_id')}, node_id={body.get('node_id')}")
    
    record = None
    try:
        # Step 1: Ingest and validate payload
        record = _with_db_recovery("ingest_sensor_payload", lambda: ingest_sensor_payload(body))
        logger.info(f"Record created with data_id={record['data_id']}, node_id={record.get('node_id')}")
        
        # Step 2: Publish job to queue with object_key for worker to fetch raw data
        job_payload = {
            "data_id": record["data_id"],
            "sensor_id": record.get("sensor_id"),
            "node_id": record.get("node_id"),
            "object_key": record.get("object_key"),
            "metrics": record.get("metrics", {}),
            "retry_count": 0,
        }
        publish_job(job_payload)
        logger.info(f"Job published for data_id={record['data_id']} with object_key={record.get('object_key')}")
        
    except ValidationError as exc:
        # Validation failed on request
        logger.warning(f"Validation error: {exc}")
        return jsonify({"error": str(exc)}), 400
        
    except BackendError as exc:
        # Backend operation failed during record creation/retrieval
        logger.error(f"Backend error: {exc}")
        return jsonify({"error": str(exc)}), 500
        
    except Exception as exc:
        # Unexpected error - try to mark record as failed if it exists
        logger.error(f"Unexpected error during ingestion: {exc}", exc_info=True)
        if record and record.get("data_id"):
            try:
                mark_failed(record["data_id"])
                logger.info(f"Marked record {record['data_id']} as failed")
            except BackendError as cleanup_exc:
                logger.error(f"Failed to mark record as failed: {cleanup_exc}")
        
        return jsonify({"error": f"Failed to enqueue processing job: {exc}"}), 500

    # Success - return 202 Accepted
    response = {
        "data_id": record["data_id"],
        "status": record.get("status", "pending")
    }
    return jsonify(response), 202


# ============================================================================
# Query Endpoints
# ============================================================================


@app.route("/summary", methods=["GET"])
def summary():
    """
    Retrieve summary statistics for a specific data upload.
    
    Query Parameters:
        id (required): The data_id to retrieve
    
    Returns:
        200 OK with full record including summary (if processing complete)
        400 Bad Request: Missing or invalid id parameter
        404 Not Found: Record with given id does not exist
        500 Internal Server Error: Database error
    """
    data_id = request.args.get("id")
    
    # Validate query parameter
    if not data_id:
        logger.warning("GET /summary called without id parameter")
        return jsonify({"error": "id is required"}), 400
    
    logger.info(f"Retrieving summary for data_id={data_id}")
    
    try:
        # Retrieve record from database
        record = _with_db_recovery("get_summary_by_id", lambda: get_summary_by_id(data_id))
        logger.info(f"Retrieved record {data_id} with status={record.get('status')}")
        
    except RecordNotFoundError:
        logger.warning(f"Record not found: {data_id}")
        return jsonify({"error": "not found"}), 404
        
    except BackendError as exc:
        logger.error(f"Backend error retrieving record {data_id}: {exc}")
        return jsonify({"error": str(exc)}), 500

    return jsonify(record), 200


@app.route("/list", methods=["GET"])
def list_uploads():
    """
    Retrieve all sensor data records.
    
    Returns list of all records regardless of processing status.
    
    Returns:
        200 OK with list of records: [{ "data_id": "...", ... }]
        500 Internal Server Error: { "error": "database error message" }
    """
    logger.info("Retrieving list of all records")
    
    try:
        records = _with_db_recovery("list_uploads", service_list_uploads)
        logger.info(f"Retrieved {len(records)} records")
        return jsonify(records), 200
        
    except BackendError as exc:
        logger.error(f"Backend error listing records: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/alerts", methods=["GET"])
def get_alerts():
    """List persisted active alerts."""
    try:
        alerts = list_alerts(active_only=True)
        return jsonify({"data": alerts}), 200
    except Exception as exc:
        logger.error(f"Error listing alerts: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/alerts/<alert_id>", methods=["DELETE"])
def dismiss_alert(alert_id: str):
    """Clear one alert by id while preserving history."""
    if not alert_id:
        return jsonify({"error": "alert_id is required"}), 400

    try:
        cleared = clear_alert(alert_id)
        if not cleared:
            return jsonify({"error": "not found"}), 404
        return jsonify({"status": "cleared", "alert_id": alert_id}), 200
    except Exception as exc:
        logger.error(f"Error clearing alert {alert_id}: {exc}")
        return jsonify({"error": str(exc)}), 500


# ============================================================================
# Error Handlers
# ============================================================================


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    logger.warning(f"404 Not Found: {request.path}")
    return jsonify({"error": "endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 Method Not Allowed errors."""
    logger.warning(f"405 Method Not Allowed: {request.method} {request.path}")
    return jsonify({"error": "method not allowed"}), 405


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server Error."""
    logger.error(f"500 Internal Server Error: {error}", exc_info=True)
    return jsonify({"error": "internal server error"}), 500


# ============================================================================
# Application Entry Point
# ============================================================================


if __name__ == "__main__":
    # Use default port for starter scaffold.
    logger.info("Starting IoT Data Aggregation API on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
