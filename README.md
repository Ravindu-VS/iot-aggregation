# IoT Data Aggregation Platform

IoT sensor data aggregation system with async processing, local-first infrastructure, and a 5-role team split.

## Overview

This project runs as a Docker Compose stack with:

- Flask API for ingestion and retrieval
- RabbitMQ queue for async jobs
- Worker service for summary processing
- DynamoDB Local for persistence
- MinIO for object-storage compatibility
- Nginx-hosted frontend dashboard

## Project Structure
 
```
api/            Flask API endpoints
backend/        Business logic, models, validation
db/             DynamoDB table access and helpers
worker/         Queue consumer and job processing
frontend/       Static UI served by nginx
shared/         Shared config and queue helpers
tests/          Unit tests
scripts/        Smoke and verification scripts
docker-compose.yml
```

## Quick Start

```powershell
docker compose up --build -d
docker compose ps
```

Service URLs:

- Frontend: http://localhost:8080
- API: http://localhost:5000
- RabbitMQ UI: http://localhost:15672
- MinIO Console: http://localhost:9001
- DynamoDB Local: http://localhost:8000

## API Endpoints

- `GET /health`
- `POST /data`
- `GET /summary?id=<data_id>`
- `GET /list`

Example `POST /data` body:

```json
{
  "sensor_id": "SENSOR-01",
  "values": [20.5, 21.0, 22.3]
}
```

## Data Flow

1. API validates and stores a new record as `pending`.
2. API publishes a job to RabbitMQ.
3. Worker consumes the job, computes summary, updates record.
4. Status transitions: `pending -> processing -> done` (or `failed` after retries).

## Testing and Verification

Run tests:

```powershell
$env:USE_LOCAL='true'
$env:DYNAMO_ENDPOINT='http://localhost:8000'
.venv/Scripts/python.exe -m pytest -q
```

Run integration smoke:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/integration_smoke.ps1
```

Run all checks (stack + tests + smoke + DB scan):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_all.ps1
```

## Team Roles

- Member 1: Lead/Integrator + Worker
- Member 2: Backend
- Member 3: API
- Member 4: Database
- Member 5: Frontend/DevOps

## Notes

- Current setup is local-first and does not require AWS accounts.
- DynamoDB is emulated with DynamoDB Local.
- Object storage uses MinIO local defaults.
- Frontend uses nginx `/api` proxy to reach the API container.

## Related Docs

- `frontend/README.md`
- `db/schema.md`
- `scripts/integration_smoke.ps1`
- `scripts/verify_all.ps1`
##Thankyou
