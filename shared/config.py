import os

QUEUE_NAME = os.getenv("QUEUE_NAME", "iot-jobs")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
MAX_JOB_RETRIES = int(os.getenv("MAX_JOB_RETRIES", "3"))
RETRY_BACKOFF_SECONDS = int(os.getenv("RETRY_BACKOFF_SECONDS", "2"))

BUCKET_NAME = os.getenv("BUCKET_NAME", "iot-data-bucket")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

DYNAMO_TABLE = os.getenv("DYNAMO_TABLE", "iot_data")
ALERTS_TABLE = os.getenv("ALERTS_TABLE", "iot_alerts")
DYNAMO_ENDPOINT = os.getenv("DYNAMO_ENDPOINT", "http://dynamodb-local:8000")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

API_PORT = int(os.getenv("API_PORT", "5000"))
USE_LOCAL = os.getenv("USE_LOCAL", "true").lower() == "true"
