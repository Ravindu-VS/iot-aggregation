from backend.exceptions import ValidationError
from backend.models import NormalizedPayload


def validate_sensor_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValidationError("Payload must be a dictionary")

    # --- node_id checks ---
    if "node_id" not in payload:
        raise ValidationError("node_id is required")

    node_id = payload["node_id"]
    if not isinstance(node_id, str):
        raise ValidationError("node_id must be a string")

    if not node_id.strip():
        raise ValidationError("node_id must not be empty or whitespace")

    # --- sensor_id checks ---
    if "sensor_id" not in payload:
        raise ValidationError("sensor_id is required")

    sensor_id = payload["sensor_id"]
    if not isinstance(sensor_id, str):
        raise ValidationError("sensor_id must be a string")

    if not sensor_id.strip():
        raise ValidationError("sensor_id must not be empty or whitespace")

    # --- metrics checks (new structure) ---
    if "metrics" in payload:
        metrics = payload["metrics"]
        if not isinstance(metrics, dict):
            raise ValidationError("metrics must be a dictionary")
        for key, val in metrics.items():
            if not isinstance(key, str):
                raise ValidationError("Metric names must be strings")
            if not isinstance(val, (int, float)):
                raise ValidationError(f"Metric '{key}' must be numeric, got {type(val).__name__}")

    # --- values checks (legacy, for backward compatibility) ---
    if "values" in payload:
        values = payload["values"]
        if not isinstance(values, list):
            raise ValidationError("values must be a list")

        if len(values) == 0:
            raise ValidationError("values must not be empty")

        for idx, v in enumerate(values):
            if not isinstance(v, (int, float)):
                raise ValidationError(
                    f"All values must be numeric; got {type(v).__name__} at index {idx}"
                )

    # At least one of metrics or values must be present
    if "metrics" not in payload and "values" not in payload:
        raise ValidationError("Either metrics (dict) or values (list) must be provided")


def normalize_sensor_payload(payload: dict) -> NormalizedPayload:
    """Normalize payload to handle both legacy (values) and new (metrics) formats."""
    node_id = payload["node_id"].strip().upper()
    sensor_id = payload["sensor_id"].strip().upper()
    
    # Handle new metrics format
    if "metrics" in payload and payload["metrics"]:
        metrics = {k: float(v) for k, v in payload["metrics"].items()}
        values = list(metrics.values())
    else:
        # Fall back to legacy values format
        values = [float(v) for v in payload.get("values", [])]
        metrics = {}
    
    return NormalizedPayload(
        sensor_id=sensor_id,
        node_id=node_id,
        metrics=metrics,
        values=values,
    )
