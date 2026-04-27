$ErrorActionPreference = 'Stop'

Write-Host '=== 1) Start services ==='
docker compose up --build -d | Out-Host
docker compose ps | Out-Host

Write-Host '=== 2) Run unit tests ==='
$env:USE_LOCAL = 'true'
$env:DYNAMO_ENDPOINT = 'http://localhost:8000'
D:/Github/iot-aggregation/.venv/Scripts/python.exe -m pytest -q | Out-Host

Write-Host '=== 3) Run integration smoke ==='
powershell -ExecutionPolicy Bypass -File scripts/integration_smoke.ps1 | Out-Host

Write-Host '=== 4) Scan DynamoDB Local ==='
docker run --rm --network iot-aggregation_default `
  -e AWS_ACCESS_KEY_ID=fake `
  -e AWS_SECRET_ACCESS_KEY=fake `
  -e AWS_DEFAULT_REGION=us-east-1 `
  amazon/aws-cli dynamodb scan `
  --table-name iot_data `
  --endpoint-url http://dynamodb-local:8000 | Out-Host

Write-Host '=== Verification complete ==='
