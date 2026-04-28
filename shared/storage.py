"""MinIO S3-compatible object storage helper for raw sensor data."""

import json
import logging
import os

try:
    import boto3
except ImportError:
    boto3 = None

try:
    from minio import Minio
except ImportError:
    Minio = None

from shared.config import AWS_REGION, BUCKET_NAME, is_local_mode

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
BUCKET_NAME = os.getenv("BUCKET_NAME", BUCKET_NAME)


def _get_s3_client():
    if boto3 is None:
        logger.warning("boto3 not available; S3 storage disabled")
        return None
    return boto3.client("s3", region_name=AWS_REGION)


def _get_minio_client():
    """Get MinIO client, returns None if not available."""
    if Minio is None:
        logger.warning("MinIO library not available; object storage disabled")
        return None
    
    try:
        client = Minio(
            MINIO_ENDPOINT.replace("http://", "").replace("https://", ""),
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
        return client
    except Exception as exc:
        logger.warning(f"Failed to initialize MinIO client: {exc}")
        return None


def ensure_bucket_exists():
    """Create bucket if it doesn't exist."""
    if not is_local_mode():
        return True

    client = _get_minio_client()
    if client is None:
        return False
    
    try:
        if not client.bucket_exists(BUCKET_NAME):
            client.make_bucket(BUCKET_NAME)
            logger.info(f"Created bucket: {BUCKET_NAME}")
        return True
    except Exception as exc:
        logger.warning(f"Failed to ensure bucket exists: {exc}")
        return False


def store_raw_payload(object_key: str, payload: dict) -> bool:
    """
    Store raw sensor payload to object storage.
    
    Args:
        object_key: Path where to store (e.g., 'raw/NODE_TH/data-id.json')
        payload: Sensor payload data
    
    Returns:
        True if stored successfully, False otherwise
    """
    data = json.dumps(payload).encode("utf-8")

    if is_local_mode():
        client = _get_minio_client()
        if client is None:
            logger.warning(f"MinIO client unavailable; skipping object storage for {object_key}")
            return False

        try:
            client.put_object(
                BUCKET_NAME,
                object_key,
                data,
                length=len(data),
                content_type="application/json",
            )
            logger.info(f"Stored raw payload to {BUCKET_NAME}/{object_key}")
            return True
        except Exception as exc:
            logger.error(f"Failed to store object {object_key}: {exc}")
            return False

    s3 = _get_s3_client()
    if s3 is None:
        return False

    try:
        s3.put_object(Bucket=BUCKET_NAME, Key=object_key, Body=data, ContentType="application/json")
        logger.info(f"Stored raw payload to s3://{BUCKET_NAME}/{object_key}")
        return True
    except Exception as exc:
        logger.error(f"Failed to store object {object_key} in S3: {exc}")
        return False


def fetch_raw_payload(object_key: str) -> dict | None:
    """
    Fetch raw sensor payload from object storage.
    
    Args:
        object_key: Path to fetch
    
    Returns:
        Parsed payload dict, or None on error
    """
    if is_local_mode():
        client = _get_minio_client()
        if client is None:
            logger.warning(f"MinIO client unavailable; cannot fetch {object_key}")
            return None

        try:
            response = client.get_object(BUCKET_NAME, object_key)
            data = response.read().decode("utf-8")
            return json.loads(data)
        except Exception as exc:
            logger.error(f"Failed to fetch object {object_key}: {exc}")
            return None

    s3 = _get_s3_client()
    if s3 is None:
        return None

    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=object_key)
        return json.loads(response["Body"].read().decode("utf-8"))
    except Exception as exc:
        logger.error(f"Failed to fetch object {object_key} from S3: {exc}")
        return None
