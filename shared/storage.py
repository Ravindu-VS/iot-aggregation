"""MinIO S3-compatible object storage helper for raw sensor data."""

import json
import logging
import os

try:
    from minio import Minio
except ImportError:
    Minio = None

logger = logging.getLogger(__name__)

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
BUCKET_NAME = os.getenv("BUCKET_NAME", "iot-data-bucket")


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
    Store raw sensor payload to MinIO.
    
    Args:
        object_key: Path where to store (e.g., 'raw/NODE_TH/data-id.json')
        payload: Sensor payload data
    
    Returns:
        True if stored successfully, False otherwise
    """
    client = _get_minio_client()
    if client is None:
        logger.warning(f"MinIO client unavailable; skipping object storage for {object_key}")
        return False
    
    try:
        data = json.dumps(payload).encode('utf-8')
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


def fetch_raw_payload(object_key: str) -> dict | None:
    """
    Fetch raw sensor payload from MinIO.
    
    Args:
        object_key: Path to fetch
    
    Returns:
        Parsed payload dict, or None on error
    """
    client = _get_minio_client()
    if client is None:
        logger.warning(f"MinIO client unavailable; cannot fetch {object_key}")
        return None
    
    try:
        response = client.get_object(BUCKET_NAME, object_key)
        data = response.read().decode('utf-8')
        return json.loads(data)
    except Exception as exc:
        logger.error(f"Failed to fetch object {object_key}: {exc}")
        return None
