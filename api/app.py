from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
import sys
import logging
import os

# ============================================
# PATH SETUP
# ============================================

sys.path.insert(0, "/app")

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

# ============================================
# APP CONFIG
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================
# 🔥 CORS (IMPORTANT FOR AMPLIFY FRONTEND)
# ============================================

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=False,
    methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ============================================
# ENV CONFIG
# ============================================

PORT = int(os.environ.get("PORT", 5000))

# ============================================
# DB INIT SAFETY
# ============================================

_db_initialized = False


def _ensure_db_initialized():
    global _db_initialized
    if not _db_initialized:
        try:
            create_table_if_not_exists()
            create_alerts_table_if_not_exists()
            _db_initialized = True
            logger.info("Database initialized successfully")
        except Exception as exc:
            logger.warning(f"DB init failed: {exc}")


def _with_db_recovery(operation_name: str, operation):
    global _db_initialized

    try:
        return operation()

    except BackendError as exc:
        if "ResourceNotFoundException" not in str(exc):
            raise

        logger.warning(f"{operation_name} failed, retrying DB init")

        try:
            create_table_if_not_exists()
            create_alerts_table_if_not_exists()
            _db_initialized = True
        except Exception as init_exc:
            logger.error(f"DB recovery failed: {init_exc}")
            raise

        return operation()

# ============================================
# HEALTH CHECK
# ============================================

@app.route("/health", methods=["GET"])
def health():
    _ensure_db_initialized()
    return jsonify({"status": "ok"}), 200


# ============================================
# INGEST DATA
# ============================================

@app.route("/data", methods=["POST"])
def receive_data():
    body = request.get_json(silent=True) or {}

    logger.info(f"Incoming data sensor={body.get('sensor_id')} node={body.get('node_id')}")

    record = None

    try:
        record = _with_db_recovery(
            "ingest_sensor_payload",
            lambda: ingest_sensor_payload(body)
        )

        job_payload = {
            "data_id": record["data_id"],
            "sensor_id": record.get("sensor_id"),
            "node_id": record.get("node_id"),
            "object_key": record.get("object_key"),
            "metrics": record.get("metrics", {}),
            "retry_count": 0,
        }

        publish_job(job_payload)

    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    except BackendError as exc:
        return jsonify({"error": str(exc)}), 500

    except Exception as exc:
        logger.error(f"Unexpected error: {exc}", exc_info=True)

        if record and record.get("data_id"):
            try:
                mark_failed(record["data_id"])
            except Exception:
                pass

        return jsonify({"error": "internal server error"}), 500

    return jsonify({
        "data_id": record["data_id"],
        "status": record.get("status", "pending")
    }), 202


# ============================================
# SUMMARY
# ============================================

@app.route("/summary", methods=["GET"])
def summary():
    data_id = request.args.get("id")

    if not data_id:
        return jsonify({"error": "id is required"}), 400

    try:
        record = _with_db_recovery(
            "get_summary_by_id",
            lambda: get_summary_by_id(data_id)
        )
        return jsonify(record), 200

    except RecordNotFoundError:
        return jsonify({"error": "not found"}), 404

    except BackendError as exc:
        return jsonify({"error": str(exc)}), 500


# ============================================
# LIST
# ============================================

@app.route("/list", methods=["GET"])
def list_uploads():
    try:
        records = _with_db_recovery("list_uploads", service_list_uploads)
        return jsonify({"data": records}), 200
    except BackendError as exc:
        return jsonify({"error": str(exc)}), 500


# ============================================
# ALERTS
# ============================================

@app.route("/alerts", methods=["GET"])
def get_alerts():
    try:
        alerts = list_alerts(active_only=True)
        return jsonify({"data": alerts}), 200
    except Exception as exc:
        logger.error(f"Alerts error: {exc}")
        return jsonify({"error": "failed to load alerts"}), 500


@app.route("/alerts/<alert_id>", methods=["DELETE"])
def dismiss_alert(alert_id):
    try:
        cleared = clear_alert(alert_id)
        if not cleared:
            return jsonify({"error": "not found"}), 404

        return jsonify({"status": "cleared", "alert_id": alert_id}), 200

    except Exception as exc:
        logger.error(f"Alert delete error: {exc}")
        return jsonify({"error": "failed to clear alert"}), 500


# ============================================
# API PREFIX PASSTHROUGH
# ============================================

@app.route("/api/<path:path>", methods=["GET", "POST", "DELETE", "OPTIONS"])
def api_prefix_passthrough(path):
    """Handle /api/X requests by redirecting to /X.
    Defense-in-depth: Nginx strips /api, but direct access still works."""
    qs = request.query_string.decode()
    target = f"/{path}"
    if qs:
        target += f"?{qs}"
    return redirect(target, code=307)


# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "endpoint not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "internal server error"}), 500


# ============================================
# ENTRY POINT (EC2 SAFE)
# ============================================

if __name__ == "__main__":
    logger.info(f"Starting backend on 0.0.0.0:{PORT}")

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
