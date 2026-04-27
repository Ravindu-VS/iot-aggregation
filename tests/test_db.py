from db import database, alerts


def _configure_local_dynamo_for_host_tests():
    database.DYNAMO_ENDPOINT = "http://localhost:8000"
    database.USE_LOCAL = True
    database._table = None
    alerts.DYNAMO_ENDPOINT = "http://localhost:8000"
    alerts.USE_LOCAL = True
    alerts._table = None


def test_insert_record_stores_data():
    _configure_local_dynamo_for_host_tests()
    data_id = "test-id"
    database.insert_record(data_id, "sensor-1", "NODE_TH", "uploads/test-id.json")
    record = database.get_record(data_id)
    assert record is not None
    assert record["data_id"] == data_id


def test_upsert_alert_creates_new_alert():
    _configure_local_dynamo_for_host_tests()
    alert_data = {
        "alert_id": "test-data-id:temperature",
        "data_id": "test-data-id",
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
        "timestamp": "2025-04-21T10:30:45.123Z"
    }
    
    alerts.upsert_alert(alert_data)
    alert = alerts.get_alert(alert_data["alert_id"])
    assert alert is not None
    assert alert["alert_id"] == alert_data["alert_id"]
    assert alert["status"] == "active"
    assert alert["cleared_at"] is None


def test_upsert_alert_updates_existing_alert():
    _configure_local_dynamo_for_host_tests()
    alert_id = "test-data-id:temperature"
    initial_data = {
        "alert_id": alert_id,
        "data_id": "test-data-id",
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
        "timestamp": "2025-04-21T10:30:45.123Z"
    }
    
    # Create initial alert
    alerts.upsert_alert(initial_data)
    
    # Update with new value
    updated_data = initial_data.copy()
    updated_data["value"] = 50.0
    updated_data["message"] = "exceeded threshold (40.0 °C)"
    alerts.upsert_alert(updated_data)
    
    alert = alerts.get_alert(alert_id)
    assert alert["value"] == 50.0
    assert alert["status"] == "active"


def test_list_alerts_returns_active_alerts():
    _configure_local_dynamo_for_host_tests()
    # Create multiple alerts
    alert1 = {
        "alert_id": "SENSOR-TH-01:temperature",
        "data_id": "data1",
        "node_id": "NODE_TH",
        "sensor_id": "SENSOR-TH-01",
        "metric": "temperature",
        "value": 45.5,
        "message": "exceeded threshold",
        "threshold": {"type": "high", "value": 40.0, "unit": "°C", "label": "Temperature"},
        "timestamp": "2025-04-21T10:30:45.123Z"
    }
    alert2 = {
        "alert_id": "SENSOR-TH-01:humidity",
        "data_id": "data2",
        "node_id": "NODE_TH",
        "sensor_id": "SENSOR-TH-01",
        "metric": "humidity",
        "value": 90.0,
        "message": "exceeded threshold",
        "threshold": {"type": "high", "value": 80.0, "unit": "%", "label": "Humidity"},
        "timestamp": "2025-04-21T10:35:45.123Z"
    }
    
    alerts.upsert_alert(alert1)
    alerts.upsert_alert(alert2)
    
    active_alerts = alerts.list_alerts(active_only=True)
    assert len(active_alerts) >= 2  # May have alerts from other tests
    alert_ids = [a["alert_id"] for a in active_alerts]
    assert alert1["alert_id"] in alert_ids
    assert alert2["alert_id"] in alert_ids


def test_clear_alert_marks_as_cleared():
    _configure_local_dynamo_for_host_tests()
    alert_id = "SENSOR-TH-01:temperature"
    alert_data = {
        "alert_id": alert_id,
        "data_id": "clear-test-data-id",
        "node_id": "NODE_TH",
        "sensor_id": "SENSOR-TH-01",
        "metric": "temperature",
        "value": 45.5,
        "message": "exceeded threshold (40.0 °C)",
        "threshold": {"type": "high", "value": 40.0, "unit": "°C", "label": "Temperature"},
        "timestamp": "2025-04-21T10:30:45.123Z"
    }
    
    # Create alert
    alerts.upsert_alert(alert_data)
    
    # Clear it
    cleared_alert = alerts.clear_alert(alert_id)
    assert cleared_alert["status"] == "cleared"
    assert cleared_alert["cleared_at"] is not None
    
    # Verify it's cleared
    alert = alerts.get_alert(alert_id)
    assert alert["status"] == "cleared"
    assert alert["cleared_at"] is not None
    
    # Should not appear in active alerts
    active_alerts = alerts.list_alerts(active_only=True)
    active_ids = [a["alert_id"] for a in active_alerts]
    assert alert_id not in active_ids


def test_get_alert_returns_none_for_nonexistent():
    _configure_local_dynamo_for_host_tests()
    alert = alerts.get_alert("nonexistent-alert-id")
    assert alert is None


def test_clear_alert_returns_none_for_nonexistent():
    _configure_local_dynamo_for_host_tests()
    result = alerts.clear_alert("nonexistent-alert-id")
    assert result is None
