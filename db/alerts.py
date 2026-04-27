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


ALERTS_TABLE_NAME = os.getenv("ALERTS_TABLE", "iot_alerts")
ALERT_STATES_TABLE_NAME = os.getenv("ALERT_STATES_TABLE", "iot_alert_states")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DYNAMO_ENDPOINT = os.getenv("DYNAMO_ENDPOINT", "http://dynamodb-local:8000")
USE_LOCAL = os.getenv("USE_LOCAL", "true").lower() == "true"

_IN_MEMORY_ALERTS: dict[str, dict] = {}
_IN_MEMORY_ALERT_STATES: dict[str, dict] = {}
_alerts_table = None
_alert_states_table = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _using_in_memory() -> bool:
    return boto3 is None


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


def _build_boto_kwargs() -> dict:
    kwargs = {"region_name": AWS_REGION}
    if USE_LOCAL and DYNAMO_ENDPOINT:
        kwargs["endpoint_url"] = DYNAMO_ENDPOINT
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "fake")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "fake")
    return kwargs


def _get_alerts_table():
    global _alerts_table
    if _using_in_memory():
        return None
    if _alerts_table is None:
        dynamodb = boto3.resource("dynamodb", **_build_boto_kwargs())
        _alerts_table = dynamodb.Table(ALERTS_TABLE_NAME)
    return _alerts_table


def _get_alert_states_table():
    global _alert_states_table
    if _using_in_memory():
        return None
    if _alert_states_table is None:
        dynamodb = boto3.resource("dynamodb", **_build_boto_kwargs())
        _alert_states_table = dynamodb.Table(ALERT_STATES_TABLE_NAME)
    return _alert_states_table


def create_alerts_table_if_not_exists() -> bool:
    if _using_in_memory():
        return True

    client = boto3.client("dynamodb", **_build_boto_kwargs())
    try:
        client.create_table(
            TableName=ALERTS_TABLE_NAME,
            KeySchema=[{"AttributeName": "alert_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "alert_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
    except Exception as exc:
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code")
            if code == "ResourceInUseException":
                return True
        raise
    return True


def create_alert_states_table_if_not_exists() -> bool:
    if _using_in_memory():
        return True

    client = boto3.client("dynamodb", **_build_boto_kwargs())
    try:
        client.create_table(
            TableName=ALERT_STATES_TABLE_NAME,
            KeySchema=[{"AttributeName": "state_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "state_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
    except Exception as exc:
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code")
            if code == "ResourceInUseException":
                return True
        raise
    return True


def upsert_alert(alert: dict) -> None:
    item = {
        **alert,
        "status": alert.get("status", "active"),
        "timestamp": alert.get("timestamp", _now_iso()),
        "cleared_at": alert.get("cleared_at"),
    }

    if _using_in_memory():
        _IN_MEMORY_ALERTS[item["alert_id"]] = item
        return

    _get_alerts_table().put_item(Item=_to_dynamo_value(item))


def get_alert(alert_id: str) -> dict | None:
    if _using_in_memory():
        return _IN_MEMORY_ALERTS.get(alert_id)

    response = _get_alerts_table().get_item(Key={"alert_id": alert_id})
    item = response.get("Item")
    return _from_dynamo_value(item) if item else None


def get_alert_state(state_id: str) -> dict | None:
    if _using_in_memory():
        return _IN_MEMORY_ALERT_STATES.get(state_id)

    response = _get_alert_states_table().get_item(Key={"state_id": state_id})
    item = response.get("Item")
    return _from_dynamo_value(item) if item else None


def upsert_alert_state(state: dict) -> None:
    item = {
        **state,
        "timestamp": state.get("timestamp", _now_iso()),
    }

    if _using_in_memory():
        _IN_MEMORY_ALERT_STATES[item["state_id"]] = item
        return

    _get_alert_states_table().put_item(Item=_to_dynamo_value(item))


def list_alerts(active_only: bool = True) -> list[dict]:
    if _using_in_memory():
        values = list(_IN_MEMORY_ALERTS.values())
    else:
        response = _get_alerts_table().scan()
        values = [_from_dynamo_value(item) for item in response.get("Items", [])]

    if active_only:
        values = [item for item in values if item.get("status") == "active"]

    values.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return values


def clear_alert(alert_id: str) -> dict | None:
    if _using_in_memory():
        alert = _IN_MEMORY_ALERTS.get(alert_id)
        if not alert:
            return None
        alert["status"] = "cleared"
        alert["cleared_at"] = _now_iso()
        return alert

    table = _get_alerts_table()
    response = table.get_item(Key={"alert_id": alert_id})
    existing = response.get("Item")
    if not existing:
        return None

    table.update_item(
        Key={"alert_id": alert_id},
        UpdateExpression="SET #status = :status, cleared_at = :cleared_at",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "cleared",
            ":cleared_at": _to_dynamo_value(_now_iso()),
        },
    )

    updated = table.get_item(Key={"alert_id": alert_id}).get("Item")
    return _from_dynamo_value(updated) if updated else None
