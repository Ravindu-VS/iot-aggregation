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

_IN_MEMORY_STORE: dict[str, dict] = {}
_table = None
_table_signature: tuple[str, bool, str] | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _table_name() -> str:
    return os.getenv("DYNAMO_TABLE", "iot_data")


def _aws_region() -> str:
    return os.getenv("AWS_REGION", "us-east-1")


def _dynamo_endpoint() -> str:
    return os.getenv("DYNAMO_ENDPOINT", "http://dynamodb-local:8000")


def _is_local_mode() -> bool:
    return os.getenv("USE_LOCAL", "true").strip().lower() == "true"


def _build_boto_kwargs() -> dict:
    kwargs = {"region_name": _aws_region()}
    endpoint = _dynamo_endpoint()
    if _is_local_mode() and endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID", "fake")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY", "fake")
    return kwargs


def _get_table():
    global _table, _table_signature
    if _using_in_memory():
        return None
    signature = (_table_name(), _is_local_mode(), _dynamo_endpoint())
    if _table is None or _table_signature != signature:
        dynamodb = boto3.resource("dynamodb", **_build_boto_kwargs())
        _table = dynamodb.Table(_table_name())
        _table_signature = signature
    return _table


def create_table_if_not_exists() -> bool:
    if _using_in_memory():
        return True

    client = boto3.client("dynamodb", **_build_boto_kwargs())
    try:
        client.create_table(
            TableName=_table_name(),
            KeySchema=[{"AttributeName": "data_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "data_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
    except Exception as exc:
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code")
            if code == "ResourceInUseException":
                return True
        raise
    return True


def insert_record(data_id: str, sensor_id: str, node_id: str, object_key: str, metrics: dict = None):
    if metrics is None:
        metrics = {}
    
    item = {
        "data_id": data_id,
        "sensor_id": sensor_id,
        "node_id": node_id,
        "object_key": object_key,
        "status": "pending",
        "summary": {},
        "metrics": metrics,
        "timestamp": _now_iso(),
    }
    if _using_in_memory():
        _IN_MEMORY_STORE[data_id] = item
        return

    _get_table().put_item(Item=_to_dynamo_value(item))


def update_record_status(data_id: str, status: str):
    if _using_in_memory():
        if data_id in _IN_MEMORY_STORE:
            _IN_MEMORY_STORE[data_id]["status"] = status
        return

    _get_table().update_item(
        Key={"data_id": data_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
    )


def update_record_summary(data_id: str, summary: dict):
    if _using_in_memory():
        if data_id in _IN_MEMORY_STORE:
            _IN_MEMORY_STORE[data_id]["summary"] = summary
            _IN_MEMORY_STORE[data_id]["status"] = "done"
        return

    _get_table().update_item(
        Key={"data_id": data_id},
        UpdateExpression="SET summary = :sum, #s = :done",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":sum": _to_dynamo_value(summary), ":done": "done"},
    )


def get_record(data_id: str):
    if _using_in_memory():
        return _IN_MEMORY_STORE.get(data_id)

    response = _get_table().get_item(Key={"data_id": data_id})
    item = response.get("Item")
    if item is None:
        return None
    return _from_dynamo_value(item)


def list_records():
    if _using_in_memory():
        return list(_IN_MEMORY_STORE.values())

    response = _get_table().scan()
    return [_from_dynamo_value(item) for item in response.get("Items", [])]