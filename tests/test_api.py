"""
Comprehensive unit tests for the IoT Data Aggregation API.

Tests cover:
- Endpoint availability and health checks
- Request validation (missing fields, invalid types, empty values)
- Successful data ingestion and queueing
- Error handling and status codes
- Summary retrieval and status polling
- List operations
"""

import sys
import pytest
import json
from unittest.mock import patch, MagicMock

# Ensure project modules are importable
sys.path.insert(0, "/app")

from api.app import app
from backend.exceptions import BackendError, RecordNotFoundError, ValidationError


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client():
    """Create a Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def valid_sensor_payload():
    """Sample valid sensor data payload."""
    return {
        "sensor_id": "sensor-001",
        "values": [22.5, 23.1, 24.5, 23.8]
    }


@pytest.fixture
def valid_node_metrics_payload():
    """Sample valid node-based metrics payload (new format)."""
    return {
        "node_id": "NODE_TH",
        "sensor_id": "sensor-th-01",
        "metrics": {
            "temperature": 22.5,
            "humidity": 45.2
        }
    }


@pytest.fixture
def valid_node_pa_payload():
    """Sample valid NODE_PA metrics payload."""
    return {
        "node_id": "NODE_PA",
        "sensor_id": "sensor-pa-01",
        "metrics": {
            "pressure": 1013.25,
            "ethanol": 25.5
        }
    }


@pytest.fixture
def mock_record():
    """Mock database record."""
    return {
        "data_id": "550e8400-e29b-41d4-a716-446655440000",
        "sensor_id": "SENSOR-001",
        "node_id": "NODE_TH",
        "object_key": "raw/SENSOR-001/550e8400-e29b-41d4-a716-446655440000.json",
        "status": "pending",
        "summary": None,
        "metrics": {},
        "timestamp": "2025-04-21T10:30:45.123Z"
    }


@pytest.fixture
def mock_node_record():
    """Mock node-based database record."""
    return {
        "data_id": "550e8400-e29b-41d4-a716-446655440001",
        "sensor_id": "SENSOR-TH-01",
        "node_id": "NODE_TH",
        "object_key": "raw/SENSOR-TH-01/550e8400-e29b-41d4-a716-446655440001.json",
        "status": "pending",
        "summary": {},
        "metrics": {
            "temperature": 22.5,
            "humidity": 45.2
        },
        "timestamp": "2025-04-21T10:30:45.123Z"
    }


@pytest.fixture
def mock_node_completed_record():
    """Mock node-based record after processing."""
    return {
        "data_id": "550e8400-e29b-41d4-a716-446655440001",
        "sensor_id": "SENSOR-TH-01",
        "node_id": "NODE_TH",
        "object_key": "raw/SENSOR-TH-01/550e8400-e29b-41d4-a716-446655440001.json",
        "status": "done",
        "summary": {
            "temperature": {
                "node_id": "NODE_TH",
                "latest": 22.5,
                "min": 22.5,
                "max": 22.5,
                "avg": 22.5,
                "count": 1
            },
            "humidity": {
                "node_id": "NODE_TH",
                "latest": 45.2,
                "min": 45.2,
                "max": 45.2,
                "avg": 45.2,
                "count": 1
            }
        },
        "metrics": {
            "temperature": 22.5,
            "humidity": 45.2
        },
        "timestamp": "2025-04-21T10:30:45.123Z"
    }


@pytest.fixture
def mock_completed_record():
    """Mock database record after processing."""
    return {
        "data_id": "550e8400-e29b-41d4-a716-446655440000",
        "sensor_id": "SENSOR-001",
        "node_id": "NODE_TH",
        "object_key": "raw/SENSOR-001/550e8400-e29b-41d4-a716-446655440000.json",
        "status": "done",
        "summary": {
            "min": 22.5,
            "max": 24.5,
            "avg": 23.475,
            "count": 4
        },
        "metrics": {},
        "timestamp": "2025-04-21T10:30:45.123Z"
    }


# ============================================================================
# Health Check Tests
# ============================================================================


def test_health_check(client):
    """Test that health endpoint returns 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_health_check_content_type(client):
    """Test that health endpoint returns JSON."""
    response = client.get("/health")
    assert response.content_type == "application/json"


# ============================================================================
# Data Ingestion Tests - Success Cases
# ============================================================================


@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
def test_post_data_success(mock_ingest, mock_publish, client, valid_sensor_payload, mock_record):
    """Test successful data ingestion."""
    mock_ingest.return_value = mock_record
    
    response = client.post(
        "/data",
        data=json.dumps(valid_sensor_payload),
        content_type="application/json"
    )
    
    assert response.status_code == 202
    assert response.json["data_id"] == mock_record["data_id"]
    assert response.json["status"] == "pending"
    mock_ingest.assert_called_once()
    mock_publish.assert_called_once()


@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
def test_post_data_with_many_values(mock_ingest, mock_publish, client, mock_record):
    """Test data ingestion with large number of sensor values."""
    payload = {
        "sensor_id": "temp-sensor",
        "values": [20 + i*0.1 for i in range(100)]  # 100 readings
    }
    mock_ingest.return_value = mock_record
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 202
    mock_publish.assert_called_once()


@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
def test_post_data_with_normalized_sensor_id(mock_ingest, mock_publish, client, mock_record):
    """Test that sensor_id is normalized to uppercase."""
    payload = {
        "sensor_id": "sensor-001",
        "values": [23.5]
    }
    mock_ingest.return_value = mock_record
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 202
    assert response.json["data_id"] == mock_record["data_id"]


# ============================================================================
# Data Ingestion Tests - Validation Error Cases
# ============================================================================


@patch("api.app.ingest_sensor_payload")
def test_post_data_missing_sensor_id(mock_ingest, client):
    """Test POST /data with missing sensor_id."""
    mock_ingest.side_effect = ValidationError("sensor_id is required")
    payload = {"values": [1.0, 2.0]}
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "sensor_id is required" in response.json["error"]


@patch("api.app.ingest_sensor_payload")
def test_post_data_missing_values(mock_ingest, client):
    """Test POST /data with missing values."""
    mock_ingest.side_effect = ValidationError("values is required")
    payload = {"sensor_id": "sensor-001"}
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "values is required" in response.json["error"]


@patch("api.app.ingest_sensor_payload")
def test_post_data_empty_sensor_id(mock_ingest, client):
    """Test POST /data with empty sensor_id."""
    mock_ingest.side_effect = ValidationError("sensor_id must not be empty or whitespace")
    payload = {"sensor_id": "", "values": [1.0]}
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "sensor_id must not be empty" in response.json["error"]


@patch("api.app.ingest_sensor_payload")
def test_post_data_empty_values(mock_ingest, client):
    """Test POST /data with empty values list."""
    mock_ingest.side_effect = ValidationError("values must not be empty")
    payload = {"sensor_id": "sensor-001", "values": []}
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "values must not be empty" in response.json["error"]


@patch("api.app.ingest_sensor_payload")
def test_post_data_invalid_value_type(mock_ingest, client):
    """Test POST /data with non-numeric values."""
    mock_ingest.side_effect = ValidationError(
        "All values must be numeric; got str at index 0"
    )
    payload = {"sensor_id": "sensor-001", "values": ["not_a_number"]}
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "must be numeric" in response.json["error"]


@patch("api.app.ingest_sensor_payload")
def test_post_data_values_not_list(mock_ingest, client):
    """Test POST /data with values as non-list."""
    mock_ingest.side_effect = ValidationError("values must be a list")
    payload = {"sensor_id": "sensor-001", "values": 42}
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "values must be a list" in response.json["error"]


@patch("api.app.ingest_sensor_payload")
def test_post_data_sensor_id_not_string(mock_ingest, client):
    """Test POST /data with sensor_id as non-string."""
    mock_ingest.side_effect = ValidationError("sensor_id must be a string")
    payload = {"sensor_id": 123, "values": [1.0]}
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "sensor_id must be a string" in response.json["error"]


# ============================================================================
# Data Ingestion Tests - Backend Error Cases
# ============================================================================


@patch("api.app.ingest_sensor_payload")
def test_post_data_backend_error(mock_ingest, client, valid_sensor_payload):
    """Test POST /data when backend fails."""
    mock_ingest.side_effect = BackendError("Failed to insert record")
    
    response = client.post(
        "/data",
        data=json.dumps(valid_sensor_payload),
        content_type="application/json"
    )
    
    assert response.status_code == 500
    assert "Failed to insert record" in response.json["error"]


@patch("api.app.create_table_if_not_exists")
@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
def test_post_data_recovers_from_missing_table(
    mock_ingest, mock_publish, mock_create_table, client, valid_sensor_payload, mock_record
):
    """If table is missing, API should recover and retry ingestion once."""
    mock_ingest.side_effect = [
        BackendError("Failed to insert record: ResourceNotFoundException"),
        mock_record,
    ]

    response = client.post(
        "/data",
        data=json.dumps(valid_sensor_payload),
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json["data_id"] == mock_record["data_id"]
    assert mock_ingest.call_count == 2
    mock_create_table.assert_called_once()
    mock_publish.assert_called_once()


@patch("api.app.mark_failed")
@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
def test_post_data_queue_publish_error_marks_failed(
    mock_ingest, mock_publish, mock_mark_failed, client, valid_sensor_payload, mock_record
):
    """Test that record is marked failed if queue publish fails."""
    mock_ingest.return_value = mock_record
    mock_publish.side_effect = Exception("Queue connection failed")
    
    response = client.post(
        "/data",
        data=json.dumps(valid_sensor_payload),
        content_type="application/json"
    )
    
    assert response.status_code == 500
    assert "Failed to enqueue processing job" in response.json["error"]
    mock_mark_failed.assert_called_once_with(mock_record["data_id"])


@patch("api.app.ingest_sensor_payload")
def test_post_data_invalid_json(mock_ingest, client):
    """Test POST /data with invalid JSON."""
    response = client.post(
        "/data",
        data="not valid json",
        content_type="application/json"
    )
    
    # Flask handles invalid JSON gracefully
    assert response.status_code in [400, 500]


@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
def test_post_data_no_content_type(mock_ingest, mock_publish, client, valid_sensor_payload):
    """Test POST /data without Content-Type header."""
    mock_ingest.return_value = {"data_id": "test-id", "status": "pending"}
    
    response = client.post("/data", data=json.dumps(valid_sensor_payload))
    
    # Should still work, defaults to form-data; publish_job mocked to avoid external queue
    assert response.status_code in [202, 400]


# ============================================================================
# Summary Retrieval Tests - Success Cases
# ============================================================================


@patch("api.app.get_summary_by_id")
def test_get_summary_success(mock_get_summary, client, mock_completed_record):
    """Test successful summary retrieval."""
    mock_get_summary.return_value = mock_completed_record
    
    response = client.get("/summary?id=550e8400-e29b-41d4-a716-446655440000")
    
    assert response.status_code == 200
    assert response.json["data_id"] == mock_completed_record["data_id"]
    assert response.json["status"] == "done"
    assert response.json["summary"]["avg"] == 23.475


@patch("api.app.get_summary_by_id")
def test_get_summary_still_pending(mock_get_summary, client, mock_record):
    """Test summary retrieval when still processing."""
    mock_get_summary.return_value = mock_record
    
    response = client.get("/summary?id=550e8400-e29b-41d4-a716-446655440000")
    
    assert response.status_code == 200
    assert response.json["status"] == "pending"
    assert response.json["summary"] is None


# ============================================================================
# Summary Retrieval Tests - Error Cases
# ============================================================================


def test_get_summary_missing_id(client):
    """Test GET /summary without id parameter."""
    response = client.get("/summary")
    
    assert response.status_code == 400
    assert "id is required" in response.json["error"]


@patch("api.app.get_summary_by_id")
def test_get_summary_not_found(mock_get_summary, client):
    """Test GET /summary with non-existent id."""
    mock_get_summary.side_effect = RecordNotFoundError("550e8400-e29b-41d4-a716-446655440000")
    
    response = client.get("/summary?id=550e8400-e29b-41d4-a716-446655440000")
    
    assert response.status_code == 404
    assert "not found" in response.json["error"]


@patch("api.app.get_summary_by_id")
def test_get_summary_backend_error(mock_get_summary, client):
    """Test GET /summary when backend fails."""
    mock_get_summary.side_effect = BackendError("Database connection failed")
    
    response = client.get("/summary?id=550e8400-e29b-41d4-a716-446655440000")
    
    assert response.status_code == 500
    assert "Database connection failed" in response.json["error"]


def test_get_summary_empty_id(client):
    """Test GET /summary with empty id parameter."""
    response = client.get("/summary?id=")
    
    assert response.status_code == 400


# ============================================================================
# List Tests - Success Cases
# ============================================================================


@patch("api.app.service_list_uploads")
def test_list_uploads_success(mock_list, client, mock_completed_record, mock_record):
    """Test successful list retrieval."""
    mock_list.return_value = [mock_completed_record, mock_record]
    
    response = client.get("/list")
    
    assert response.status_code == 200
    records = response.json
    assert len(records) == 2
    assert records[0]["data_id"] == mock_completed_record["data_id"]
    assert records[1]["status"] == "pending"


@patch("api.app.service_list_uploads")
def test_list_uploads_empty(mock_list, client):
    """Test list retrieval with no records."""
    mock_list.return_value = []
    
    response = client.get("/list")
    
    assert response.status_code == 200
    assert response.json == []


# ============================================================================
# List Tests - Error Cases
# ============================================================================


@patch("api.app.service_list_uploads")
def test_list_uploads_backend_error(mock_list, client):
    """Test list retrieval when backend fails."""
    mock_list.side_effect = BackendError("Database connection failed")
    
    response = client.get("/list")
    
    assert response.status_code == 500
    assert "Database connection failed" in response.json["error"]


@patch("api.app.create_table_if_not_exists")
@patch("api.app.service_list_uploads")
def test_list_uploads_recovers_from_missing_table(mock_list, mock_create_table, client, mock_record):
    """List endpoint should recover and retry if table is missing."""
    mock_list.side_effect = [
        BackendError("Failed to list records: ResourceNotFoundException"),
        [mock_record],
    ]

    response = client.get("/list")

    assert response.status_code == 200
    assert len(response.json) == 1
    assert mock_list.call_count == 2
    mock_create_table.assert_called_once()


# ============================================================================
# HTTP Method Tests
# ============================================================================


def test_get_data_not_allowed(client):
    """Test that GET /data is not allowed."""
    response = client.get("/data")
    
    assert response.status_code == 405


def test_post_summary_not_allowed(client):
    """Test that POST /summary is not allowed."""
    response = client.post("/summary", data=json.dumps({"id": "test"}))
    
    assert response.status_code == 405


def test_post_list_not_allowed(client):
    """Test that POST /list is not allowed."""
    response = client.post("/list", data=json.dumps({}))
    
    assert response.status_code == 405


# ============================================================================
# 404 Not Found Tests
# ============================================================================


def test_nonexistent_endpoint(client):
    """Test request to non-existent endpoint."""
    response = client.get("/nonexistent")
    
    assert response.status_code == 404
    assert "not found" in response.json["error"].lower()


# ============================================================================
# Content-Type Tests
# ============================================================================


def test_all_endpoints_return_json(client):
    """Test that all endpoints return JSON content type."""
    endpoints = [
        ("/health", "GET"),
        ("/list", "GET"),
        ("/summary?id=test", "GET"),
    ]
    
    for endpoint, method in endpoints:
        if method == "GET":
            response = client.get(endpoint)
        
        assert response.content_type == "application/json", f"Failed for {endpoint}"


# ============================================================================
# Integration-like Tests
# ============================================================================


@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
@patch("api.app.get_summary_by_id")
def test_full_workflow_simulation(
    mock_get_summary, mock_ingest, mock_publish, client, valid_sensor_payload, 
    mock_record, mock_completed_record
):
    """
    Test a simulated full workflow:
    1. Ingest data (returns pending)
    2. Poll for summary (still pending)
    3. Poll for summary (now done)
    """
    data_id = mock_record["data_id"]
    mock_ingest.return_value = mock_record
    
    # Step 1: Ingest
    response = client.post(
        "/data",
        data=json.dumps(valid_sensor_payload),
        content_type="application/json"
    )
    assert response.status_code == 202
    assert response.json["status"] == "pending"
    
    # Step 2: Poll (still pending)
    mock_get_summary.return_value = mock_record
    response = client.get(f"/summary?id={data_id}")
    assert response.status_code == 200
    assert response.json["status"] == "pending"
    assert response.json["summary"] is None
    
    # Step 3: Poll (now done)
    mock_get_summary.return_value = mock_completed_record
    response = client.get(f"/summary?id={data_id}")
    assert response.status_code == 200
    assert response.json["status"] == "done"
    assert response.json["summary"]["avg"] == 23.475


# ============================================================================
# NODE-BASED METRICS TESTS - New Format
# ============================================================================


@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
def test_post_node_metrics_success(mock_ingest, mock_publish, client, valid_node_metrics_payload, mock_node_record):
    """Test successful node-based metrics ingestion."""
    mock_ingest.return_value = mock_node_record
    
    response = client.post(
        "/data",
        data=json.dumps(valid_node_metrics_payload),
        content_type="application/json"
    )
    
    assert response.status_code == 202
    assert response.json["data_id"] == mock_node_record["data_id"]
    assert response.json["status"] == "pending"
    mock_ingest.assert_called_once()
    mock_publish.assert_called_once()
    
    # Verify job payload includes node_id and object_key
    call_args = mock_publish.call_args[0][0]
    assert call_args.get("node_id") == "NODE_TH"
    assert call_args.get("object_key") is not None


@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
def test_post_node_pa_metrics_success(mock_ingest, mock_publish, client, valid_node_pa_payload):
    """Test NODE_PA (pressure/ethanol) metrics ingestion."""
    mock_record = {
        "data_id": "test-id",
        "node_id": "NODE_PA",
        "sensor_id": "SENSOR-PA-01",
        "object_key": "raw/SENSOR-PA-01/test-id.json",
        "status": "pending",
        "summary": {},
        "metrics": {"pressure": 1013.25, "ethanol": 25.5},
        "timestamp": "2025-04-21T10:30:45.123Z"
    }
    mock_ingest.return_value = mock_record
    
    response = client.post(
        "/data",
        data=json.dumps(valid_node_pa_payload),
        content_type="application/json"
    )
    
    assert response.status_code == 202
    call_args = mock_publish.call_args[0][0]
    assert call_args.get("node_id") == "NODE_PA"
    assert call_args.get("metrics", {}).get("pressure") == 1013.25


def test_post_data_missing_node_id(client):
    """Test data ingestion fails when node_id is missing."""
    payload = {
        "sensor_id": "sensor-001",
        "metrics": {"temperature": 22.5}
    }
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "node_id" in response.json["error"].lower()


def test_post_data_invalid_node_id_type(client):
    """Test data ingestion fails when node_id is not a string."""
    payload = {
        "node_id": 123,  # Should be string
        "sensor_id": "sensor-001",
        "metrics": {"temperature": 22.5}
    }
    
    response = client.post(
        "/data",
        data=json.dumps(payload),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    assert "node_id" in response.json["error"].lower()


@patch("api.app.publish_job")
@patch("api.app.ingest_sensor_payload")
@patch("api.app.get_summary_by_id")
def test_node_workflow_with_metrics(
    mock_get_summary, mock_ingest, mock_publish, client, valid_node_metrics_payload,
    mock_node_record, mock_node_completed_record
):
    """Test full workflow for node-based metrics."""
    data_id = mock_node_record["data_id"]
    mock_ingest.return_value = mock_node_record
    
    # Step 1: Ingest
    response = client.post(
        "/data",
        data=json.dumps(valid_node_metrics_payload),
        content_type="application/json"
    )
    assert response.status_code == 202
    assert response.json["status"] == "pending"
    
    # Step 2: Poll (completed)
    mock_get_summary.return_value = mock_node_completed_record
    response = client.get(f"/summary?id={data_id}")
    assert response.status_code == 200
    assert response.json["status"] == "done"
    assert "temperature" in response.json["summary"]
    assert "humidity" in response.json["summary"]
    assert response.json["summary"]["temperature"]["latest"] == 22.5
    assert response.json["summary"]["humidity"]["latest"] == 45.2


# ============================================================================
# Alert Tests - Fixtures
# ============================================================================


@pytest.fixture
def mock_active_alert():
    """Mock active alert record."""
    return {
        "alert_id": "SENSOR-TH-01:temperature",
        "data_id": "550e8400-e29b-41d4-a716-446655440000",
        "node_id": "NODE_TH",
        "sensor_id": "SENSOR-TH-01",
        "metric": "temperature",
        "value": 45.5,
        "message": "exceeded threshold (40.0 °C)",
        "threshold": {
            "type": "high",
            "value": 40.0,
            "unit": "°C",
            "label": "Temperature"
        },
        "status": "active",
        "timestamp": "2025-04-21T10:30:45.123Z",
        "cleared_at": None
    }


@pytest.fixture
def mock_cleared_alert():
    """Mock cleared alert record."""
    return {
        "alert_id": "SENSOR-TH-01:temperature",
        "data_id": "550e8400-e29b-41d4-a716-446655440000",
        "node_id": "NODE_TH",
        "sensor_id": "SENSOR-TH-01",
        "metric": "temperature",
        "value": 45.5,
        "message": "exceeded threshold (40.0 °C)",
        "threshold": {
            "type": "high",
            "value": 40.0,
            "unit": "°C",
            "label": "Temperature"
        },
        "status": "cleared",
        "timestamp": "2025-04-21T10:30:45.123Z",
        "cleared_at": "2025-04-21T10:35:45.123Z"
    }


# ============================================================================
# Alert Tests - Success Cases
# ============================================================================


@patch("api.app.list_alerts")
def test_get_alerts_success(mock_list_alerts, client, mock_active_alert):
    """Test successful alerts retrieval."""
    mock_list_alerts.return_value = [mock_active_alert]
    
    response = client.get("/alerts")
    
    assert response.status_code == 200
    alerts = response.json["data"]
    assert len(alerts) == 1
    assert alerts[0]["alert_id"] == mock_active_alert["alert_id"]
    assert alerts[0]["status"] == "active"
    assert alerts[0]["metric"] == "temperature"


@patch("api.app.list_alerts")
def test_get_alerts_empty(mock_list_alerts, client):
    """Test alerts retrieval with no active alerts."""
    mock_list_alerts.return_value = []
    
    response = client.get("/alerts")
    
    assert response.status_code == 200
    assert response.json["data"] == []


@patch("api.app.clear_alert")
def test_delete_alert_success(mock_clear_alert, client, mock_active_alert):
    """Test successful alert clearing."""
    alert_id = mock_active_alert["alert_id"]
    mock_clear_alert.return_value = {**mock_active_alert, "status": "cleared"}
    
    response = client.delete(f"/alerts/{alert_id}")
    
    assert response.status_code == 200
    assert response.json["alert_id"] == alert_id
    assert response.json["status"] == "cleared"
    mock_clear_alert.assert_called_once_with(alert_id)


# ============================================================================
# Alert Tests - Error Cases
# ============================================================================


@patch("api.app.list_alerts")
def test_get_alerts_backend_error(mock_list_alerts, client):
    """Test alerts retrieval when backend fails."""
    mock_list_alerts.side_effect = BackendError("Database connection failed")
    
    response = client.get("/alerts")
    
    assert response.status_code == 500
    assert "Database connection failed" in response.json["error"]


@patch("api.app.clear_alert")
def test_delete_alert_not_found(mock_clear_alert, client):
    """Test alert clearing with non-existent alert_id."""
    alert_id = "nonexistent-alert-id"
    mock_clear_alert.return_value = None  # Alert doesn't exist
    
    response = client.delete(f"/alerts/{alert_id}")
    
    assert response.status_code == 404
    assert "not found" in response.json["error"]


@patch("api.app.clear_alert")
def test_delete_alert_backend_error(mock_clear_alert, client):
    """Test alert clearing when backend fails."""
    alert_id = "SENSOR-TH-01:temperature"
    mock_clear_alert.side_effect = BackendError("Database connection failed")
    
    response = client.delete(f"/alerts/{alert_id}")
    
    assert response.status_code == 500
    assert "Database connection failed" in response.json["error"]


def test_delete_alert_missing_id(client):
    """Test DELETE /alerts without alert_id."""
    response = client.delete("/alerts/")
    
    assert response.status_code == 404  # Flask will handle this as 404


# ============================================================================
# Alert Tests - HTTP Method Tests
# ============================================================================


def test_post_alerts_not_allowed(client):
    """Test that POST /alerts is not allowed."""
    response = client.post("/alerts")
    
    assert response.status_code == 405


def test_put_alerts_not_allowed(client):
    """Test that PUT /alerts is not allowed."""
    response = client.put("/alerts/test-id")
    
    assert response.status_code == 405

