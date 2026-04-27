from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

try:
	import boto3
	from botocore.exceptions import ClientError
except ImportError:
	boto3 = None
	ClientError = Exception


_IN_MEMORY_ALERTS: dict[str, dict] = {}
_IN_MEMORY_ALERT_STATES: dict[str, dict] = {}

_alerts_table = None
_states_table = None
_alerts_signature: tuple[str, bool, str] | None = None
_states_signature: tuple[str, bool, str] | None = None


def _now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def _alerts_table_name() -> str:
	return os.getenv("ALERTS_TABLE", "iot_alerts")


def _alert_states_table_name() -> str:
	return os.getenv("ALERT_STATES_TABLE", "iot_alert_states")


def _aws_region() -> str:
	return os.getenv("AWS_REGION", "us-east-1")


def _dynamo_endpoint() -> str:
	return os.getenv("DYNAMO_ENDPOINT", "http://dynamodb-local:8000")


def _is_local_mode() -> bool:
	return os.getenv("USE_LOCAL", "true").strip().lower() == "true"


def _to_dynamo_value(value):
	if isinstance(value, float):
		return Decimal(str(value))
	if isinstance(value, dict):
		return {k: _to_dynamo_value(v) for k, v in value.items()}
	if isinstance(value, list):
		return [_to_dynamo_value(v) for v in value]
	return value


def _from_dynamo_value(value):
	if isinstance(value, Decimal):
		if value == value.to_integral_value():
			return int(value)
		return float(value)
	if isinstance(value, dict):
		return {k: _from_dynamo_value(v) for k, v in value.items()}
	if isinstance(value, list):
		return [_from_dynamo_value(v) for v in value]
	return value


def _using_in_memory() -> bool:
	return boto3 is None


def _build_boto_kwargs() -> dict:
	kwargs = {"region_name": _aws_region()}
	endpoint = _dynamo_endpoint()
	if _is_local_mode() and endpoint:
		kwargs["endpoint_url"] = endpoint
		kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "fake")
		kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "fake")
	return kwargs


def _get_alerts_table():
	global _alerts_table, _alerts_signature
	if _using_in_memory():
		return None

	signature = (_alerts_table_name(), _is_local_mode(), _dynamo_endpoint())
	if _alerts_table is None or _alerts_signature != signature:
		dynamodb = boto3.resource("dynamodb", **_build_boto_kwargs())
		_alerts_table = dynamodb.Table(_alerts_table_name())
		_alerts_signature = signature
	return _alerts_table


def _get_states_table():
	global _states_table, _states_signature
	if _using_in_memory():
		return None

	signature = (_alert_states_table_name(), _is_local_mode(), _dynamo_endpoint())
	if _states_table is None or _states_signature != signature:
		dynamodb = boto3.resource("dynamodb", **_build_boto_kwargs())
		_states_table = dynamodb.Table(_alert_states_table_name())
		_states_signature = signature
	return _states_table


def _create_table_if_not_exists(table_name: str, key_name: str) -> bool:
	if _using_in_memory():
		return True

	client = boto3.client("dynamodb", **_build_boto_kwargs())
	try:
		client.create_table(
			TableName=table_name,
			KeySchema=[{"AttributeName": key_name, "KeyType": "HASH"}],
			AttributeDefinitions=[{"AttributeName": key_name, "AttributeType": "S"}],
			BillingMode="PAY_PER_REQUEST",
		)
	except Exception as exc:
		if isinstance(exc, ClientError):
			code = exc.response.get("Error", {}).get("Code")
			if code == "ResourceInUseException":
				return True
		raise
	return True


def create_alerts_table_if_not_exists() -> bool:
	return _create_table_if_not_exists(_alerts_table_name(), "alert_id")


def create_alert_states_table_if_not_exists() -> bool:
	return _create_table_if_not_exists(_alert_states_table_name(), "state_id")


def upsert_alert(alert_data: dict) -> dict:
	alert_id = alert_data.get("alert_id")
	if not isinstance(alert_id, str) or not alert_id.strip():
		raise ValueError("alert_id is required")

	item = {
		"alert_id": alert_id,
		"data_id": alert_data.get("data_id"),
		"node_id": alert_data.get("node_id"),
		"sensor_id": alert_data.get("sensor_id"),
		"metric": alert_data.get("metric"),
		"value": float(alert_data.get("value", 0.0)),
		"message": alert_data.get("message", ""),
		"threshold": alert_data.get("threshold", {}),
		"status": "active",
		"timestamp": alert_data.get("timestamp") or _now_iso(),
		"cleared_at": None,
	}

	if _using_in_memory():
		_IN_MEMORY_ALERTS[alert_id] = item
		return item

	_get_alerts_table().put_item(Item=_to_dynamo_value(item))
	return item


def get_alert(alert_id: str) -> dict | None:
	if _using_in_memory():
		return _IN_MEMORY_ALERTS.get(alert_id)

	response = _get_alerts_table().get_item(Key={"alert_id": alert_id})
	item = response.get("Item")
	if not item:
		return None
	return _from_dynamo_value(item)


def list_alerts(active_only: bool = False) -> list[dict]:
	if _using_in_memory():
		items = list(_IN_MEMORY_ALERTS.values())
	else:
		response = _get_alerts_table().scan()
		items = [_from_dynamo_value(item) for item in response.get("Items", [])]

	if active_only:
		items = [item for item in items if item.get("status") == "active"]

	items.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
	return items


def clear_alert(alert_id: str) -> dict | None:
	existing = get_alert(alert_id)
	if not existing:
		return None

	existing["status"] = "cleared"
	existing["cleared_at"] = _now_iso()

	if _using_in_memory():
		_IN_MEMORY_ALERTS[alert_id] = existing
		return existing

	_get_alerts_table().put_item(Item=_to_dynamo_value(existing))
	return existing


def upsert_alert_state(state_data: dict) -> dict:
	state_id = state_data.get("state_id")
	if not isinstance(state_id, str) or not state_id.strip():
		raise ValueError("state_id is required")

	item = {
		"state_id": state_id,
		"status": state_data.get("status", "normal"),
		"sensor_id": state_data.get("sensor_id"),
		"metric": state_data.get("metric"),
		"alert_id": state_data.get("alert_id"),
		"updated_at": _now_iso(),
	}

	if _using_in_memory():
		_IN_MEMORY_ALERT_STATES[state_id] = item
		return item

	_get_states_table().put_item(Item=_to_dynamo_value(item))
	return item


def get_alert_state(state_id: str) -> dict | None:
	if _using_in_memory():
		return _IN_MEMORY_ALERT_STATES.get(state_id)

	response = _get_states_table().get_item(Key={"state_id": state_id})
	item = response.get("Item")
	if not item:
		return None
	return _from_dynamo_value(item)
