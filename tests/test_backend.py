
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.exceptions import BackendError, RecordNotFoundError, ValidationError
from backend.models import NormalizedPayload, SensorSummary, generate_object_key
from backend.services import (
    compute_metrics_summary,
    compute_summary,
    get_summary_by_id,
    ingest_sensor_payload,
    list_uploads,
    mark_completed,
    mark_failed,
    mark_processing,
)
from backend.validators import normalize_sensor_payload, validate_sensor_payload


# =========================================================================
# Fixtures & helpers
# =========================================================================

def _make_record(
    data_id: str = "test-uuid",
    sensor_id: str = "S1",
    node_id: str = "NODE_TH",
    status: str = "pending",
    summary: dict | None = None,
) -> dict:
    """Create a fake database record for testing."""
    return {
        "data_id": data_id,
        "sensor_id": sensor_id,
        "node_id": node_id,
        "object_key": f"raw/{sensor_id}/{data_id}.json",
        "status": status,
        "summary": summary or {},
        "timestamp": "2026-04-13T12:00:00Z",
    }


# =========================================================================
# Validator tests
# =========================================================================

class TestValidateSensorPayload:
    

    def test_valid_payload(self):
        """A well-formed payload should not raise."""
        validate_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1", "values": [23, 25, 27]})

    def test_valid_node_metrics_payload(self):
        """A well-formed node-based metrics payload should not raise."""
        validate_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1", "metrics": {"temperature": 22.5, "humidity": 45.0}})

    def test_missing_node_id(self):
        with pytest.raises(ValidationError, match="node_id is required"):
            validate_sensor_payload({"sensor_id": "S1", "values": [1, 2]})

    def test_missing_sensor_id(self):
        with pytest.raises(ValidationError, match="sensor_id is required"):
            validate_sensor_payload({"node_id": "NODE_TH", "values": [1, 2]})

    def test_node_id_not_string(self):
        with pytest.raises(ValidationError, match="node_id must be a string"):
            validate_sensor_payload({"node_id": 123, "sensor_id": "S1", "values": [1]})

    def test_sensor_id_not_string(self):
        with pytest.raises(ValidationError, match="sensor_id must be a string"):
            validate_sensor_payload({"node_id": "NODE_TH", "sensor_id": 123, "values": [1]})

    def test_sensor_id_empty_string(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_sensor_payload({"node_id": "NODE_TH", "sensor_id": "   ", "values": [1]})

    def test_missing_values_and_metrics(self):
        with pytest.raises(ValidationError, match="Either metrics \\(dict\\) or values \\(list\\) must be provided"):
            validate_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1"})

    def test_values_not_list(self):
        with pytest.raises(ValidationError, match="values must be a list"):
            validate_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1", "values": "not-a-list"})

    def test_empty_values(self):
        with pytest.raises(ValidationError, match="values must not be empty"):
            validate_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1", "values": []})

    def test_non_numeric_values(self):
        with pytest.raises(ValidationError, match="All values must be numeric"):
            validate_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1", "values": [1, "two", 3]})

    def test_payload_not_dict(self):
        with pytest.raises(ValidationError, match="Payload must be a dictionary"):
            validate_sensor_payload("not-a-dict")


# =========================================================================
# Normalization tests
# =========================================================================

class TestNormalizeSensorPayload:
    

    def test_trims_and_uppercases_node_id(self):
        result = normalize_sensor_payload({"node_id": "  node_th  ", "sensor_id": "s1", "values": [1]})
        assert result.node_id == "NODE_TH"
        assert result.sensor_id == "S1"

    def test_trims_sensor_id(self):
        result = normalize_sensor_payload({"node_id": "NODE_TH", "sensor_id": "  s1  ", "values": [1]})
        assert result.sensor_id == "S1"

    def test_uppercases_sensor_id(self):
        result = normalize_sensor_payload({"node_id": "NODE_TH", "sensor_id": "abc", "values": [1]})
        assert result.sensor_id == "ABC"

    def test_values_cast_to_float(self):
        result = normalize_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1", "values": [1, 2, 3]})
        assert result.node_id == "NODE_TH"
        assert result.values == [1.0, 2.0, 3.0]
        assert all(isinstance(v, float) for v in result.values)

    def test_does_not_mutate_original(self):
        original = {"node_id": "NODE_TH", "sensor_id": "  s1  ", "values": [1, 2]}
        normalize_sensor_payload(original)
        assert original["node_id"] == "NODE_TH"
        assert original["sensor_id"] == "  s1  "
        assert original["values"] == [1, 2]


# =========================================================================
# Model tests
# =========================================================================

class TestModels:
    

    def test_generate_object_key(self):
        key = generate_object_key("S1", "abc-123")
        assert key == "raw/S1/abc-123.json"

    def test_sensor_summary_to_dict(self):
        s = SensorSummary(min_value=1.0, max_value=5.0, avg_value=3.0, count=5)
        assert s.to_dict() == {"min": 1.0, "max": 5.0, "avg": 3.0, "count": 5}

    def test_normalized_payload_frozen(self):
        p = NormalizedPayload(node_id="NODE_TH", sensor_id="S1", values=[1.0])
        with pytest.raises(AttributeError):
            p.sensor_id = "S2"  # type: ignore[misc]


# =========================================================================
# Service tests — ingest
# =========================================================================

class TestIngestSensorPayload:
    

    @patch("backend.services.get_record")
    @patch("backend.services.insert_record")
    @patch("backend.services.uuid.uuid4")
    def test_successful_ingest(self, mock_uuid, mock_insert, mock_get):
        fake_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        mock_uuid.return_value = uuid.UUID(fake_uuid)
        mock_insert.return_value = None  # insert_record may return None
        expected_record = _make_record(data_id=fake_uuid, sensor_id="S1", node_id="NODE_TH")
        mock_get.return_value = expected_record

        result = ingest_sensor_payload({"node_id": "node_th", "sensor_id": " s1 ", "values": [10, 20]})

        mock_insert.assert_called_once_with(
            data_id=fake_uuid,
            sensor_id="S1",
            node_id="NODE_TH",
            object_key=f"raw/S1/{fake_uuid}.json",
            metrics={},
        )
        mock_get.assert_called_once_with(fake_uuid)
        assert result == expected_record

    def test_ingest_invalid_payload_raises(self):
        with pytest.raises(ValidationError):
            ingest_sensor_payload({"values": [1]})

    @patch("backend.services.insert_record", side_effect=RuntimeError("DB down"))
    def test_ingest_db_failure_wraps_exception(self, _mock_insert):
        with pytest.raises(BackendError, match="Failed to insert record"):
            ingest_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1", "values": [1]})

    @patch("backend.services.get_record", return_value=None)
    @patch("backend.services.insert_record", return_value=None)
    def test_ingest_get_record_returns_none_after_insert(self, _mock_insert, _mock_get):
        with pytest.raises(BackendError, match="not found after insert"):
            ingest_sensor_payload({"node_id": "NODE_TH", "sensor_id": "S1", "values": [1]})


# =========================================================================
# Service tests — list uploads
# =========================================================================

class TestListUploads:
    

    @patch("backend.services.list_records")
    def test_returns_all_records(self, mock_list):
        records = [_make_record(data_id="1"), _make_record(data_id="2")]
        mock_list.return_value = records

        result = list_uploads()

        assert result == records
        mock_list.assert_called_once()

    @patch("backend.services.list_records", return_value=[])
    def test_returns_empty_list(self, mock_list):
        assert list_uploads() == []

    @patch("backend.services.list_records", side_effect=RuntimeError("DB down"))
    def test_db_failure_raises_backend_error(self, _mock):
        with pytest.raises(BackendError, match="Failed to list records"):
            list_uploads()


# =========================================================================
# Service tests — get summary
# =========================================================================

class TestGetSummaryById:
    

    @patch("backend.services.get_record")
    def test_returns_record_when_pending(self, mock_get):
        record = _make_record(status="pending")
        mock_get.return_value = record

        result = get_summary_by_id("test-uuid")

        assert result["status"] == "pending"
        assert result["summary"] == {}

    @patch("backend.services.get_record")
    def test_returns_record_when_done(self, mock_get):
        summary = {"min": 1.0, "max": 5.0, "avg": 3.0, "count": 3}
        record = _make_record(status="done", summary=summary)
        mock_get.return_value = record

        result = get_summary_by_id("test-uuid")

        assert result["status"] == "done"
        assert result["summary"] == summary

    @patch("backend.services.get_record", return_value=None)
    def test_raises_not_found(self, _mock):
        with pytest.raises(RecordNotFoundError, match="not-exist"):
            get_summary_by_id("not-exist")

    @patch("backend.services.get_record", side_effect=RuntimeError("DB"))
    def test_db_failure_raises_backend_error(self, _mock):
        with pytest.raises(BackendError, match="Failed to retrieve record"):
            get_summary_by_id("some-id")


# =========================================================================
# Service tests — worker status helpers
# =========================================================================

class TestMarkProcessing:
    

    @patch("backend.services.update_record_status")
    @patch("backend.services.get_record")
    def test_marks_processing(self, mock_get, mock_update):
        existing_record = _make_record()
        processing_record = _make_record(status="processing")
        mock_get.side_effect = [existing_record, processing_record]
        mock_update.return_value = None

        result = mark_processing("test-uuid")

        mock_update.assert_called_once_with("test-uuid", "processing")
        assert mock_get.call_count == 2
        assert result["status"] == "processing"

    @patch("backend.services.get_record", return_value=None)
    def test_not_found_raises(self, _mock):
        with pytest.raises(RecordNotFoundError):
            mark_processing("missing-id")

    @patch("backend.services.get_record")
    @patch("backend.services.update_record_status", return_value=None)
    def test_get_record_none_after_update_raises(self, _mock_update, mock_get):
        mock_get.side_effect = [_make_record(), None]
        with pytest.raises(BackendError, match="not found after marking processing"):
            mark_processing("test-uuid")


class TestMarkCompleted:
    

    @patch("backend.services.update_record_summary")
    @patch("backend.services.get_record")
    def test_marks_done_with_summary(self, mock_get, mock_sum):
        summary = {"min": 1.0, "max": 3.0, "avg": 2.0, "count": 3}
        existing_record = _make_record()
        done_record = _make_record(status="done", summary=summary)
        # First call: _ensure_record_exists; second call: fetch after update
        mock_get.side_effect = [existing_record, done_record]

        result = mark_completed("test-uuid", summary)

        mock_sum.assert_called_once_with("test-uuid", summary)
        assert result["status"] == "done"
        assert result["summary"] == summary

    @patch("backend.services.get_record", return_value=None)
    def test_not_found_raises(self, _mock):
        with pytest.raises(RecordNotFoundError):
            mark_completed("missing-id", {})

    @patch("backend.services.get_record")
    @patch("backend.services.update_record_summary")
    def test_get_record_none_after_update_raises(self, _mock_sum, mock_get):
        # First call: record exists; second call: returns None
        mock_get.side_effect = [_make_record(), None]
        with pytest.raises(BackendError, match="not found after marking completed"):
            mark_completed("test-uuid", {"min": 1})


class TestMarkFailed:
    

    @patch("backend.services.update_record_status")
    @patch("backend.services.get_record")
    def test_marks_failed(self, mock_get, mock_update):
        existing_record = _make_record()
        failed_record = _make_record(status="failed")
        mock_get.side_effect = [existing_record, failed_record]
        mock_update.return_value = None

        result = mark_failed("test-uuid")

        mock_update.assert_called_once_with("test-uuid", "failed")
        assert mock_get.call_count == 2
        assert result["status"] == "failed"

    @patch("backend.services.get_record", return_value=None)
    def test_not_found_raises(self, _mock):
        with pytest.raises(RecordNotFoundError):
            mark_failed("missing-id")

    @patch("backend.services.get_record")
    @patch("backend.services.update_record_status", return_value=None)
    def test_get_record_none_after_update_raises(self, _mock_update, mock_get):
        mock_get.side_effect = [_make_record(), None]
        with pytest.raises(BackendError, match="not found after marking failed"):
            mark_failed("test-uuid")


# =========================================================================
# Service tests — compute summary
# =========================================================================

class TestComputeSummary:
    

    def test_basic_computation(self):
        result = compute_summary([10.0, 20.0, 30.0])
        assert result == {"min": 10.0, "max": 30.0, "avg": 20.0, "count": 3}

    def test_single_value(self):
        result = compute_summary([42.0])
        assert result == {"min": 42.0, "max": 42.0, "avg": 42.0, "count": 1}

    def test_negative_values(self):
        result = compute_summary([-5.0, 0.0, 5.0])
        assert result == {"min": -5.0, "max": 5.0, "avg": 0.0, "count": 3}

    def test_avg_rounding(self):
        result = compute_summary([1.0, 2.0, 3.0])
        assert result["avg"] == 2.0

    def test_empty_list_raises(self):
        with pytest.raises(ValidationError, match="non-empty list"):
            compute_summary([])

    def test_not_a_list_raises(self):
        with pytest.raises(ValidationError, match="non-empty list"):
            compute_summary("not-a-list")  # type: ignore[arg-type]


class TestComputeMetricsSummary:

    def test_single_metric_uses_compact_shape(self):
        result = compute_metrics_summary({"temperature": 22.5}, "NODE_TH")
        assert result == {
            "temperature": {
                "node_id": "NODE_TH",
                "latest": 22.5,
                "count": 1,
            }
        }

    def test_multiple_metrics_uses_compact_shape(self):
        result = compute_metrics_summary(
            {"pressure": 1013.25, "ethanol": 31.1},
            "NODE_PA",
        )
        assert result["pressure"] == {
            "node_id": "NODE_PA",
            "latest": 1013.25,
            "count": 1,
        }
        assert result["ethanol"] == {
            "node_id": "NODE_PA",
            "latest": 31.1,
            "count": 1,
        }

    def test_ignores_non_numeric_metric_values(self):
        result = compute_metrics_summary(
            {"temperature": 22.5, "status": "ok"},
            "NODE_TH",
        )
        assert "temperature" in result
        assert "status" not in result

