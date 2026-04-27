param(
    [string]$StackName = "iot-aggregation",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$deployRoot = Join-Path $repoRoot "deploy\aws"
$frontendRoot = Join-Path $repoRoot "frontend"
$espRoot = Join-Path $repoRoot "esp8266_sensor_nodes"
$samBuildRoot = Join-Path $repoRoot ".aws-sam"

function Clear-BucketIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BucketName
    )

    aws s3 ls "s3://$BucketName" 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Emptying bucket: $BucketName"
        aws s3 rm "s3://$BucketName" --recursive 1>$null 2>$null
    }
}

Push-Location $deployRoot
try {
    Write-Host "Starting clean SAM deployment for stack: $StackName"

    if (Test-Path $samBuildRoot) {
        Remove-Item -Path $samBuildRoot -Recurse -Force
    }

    # Check if stack exists and delete unrecoverable failed states.
    $stackStatus = ""
    try {
        $stackStatus = aws cloudformation describe-stacks `
            --stack-name $StackName `
            --region $Region `
            --query "Stacks[0].StackStatus" `
            --output text 2>$null
    } catch {
        $stackStatus = ""
        Write-Host "Stack check skipped or stack doesn't exist"
    }

    if ($stackStatus -eq "ROLLBACK_COMPLETE" -or $stackStatus -eq "DELETE_FAILED") {
        $accountId = aws sts get-caller-identity --query Account --output text
        if ($LASTEXITCODE -eq 0 -and $accountId) {
            Clear-BucketIfExists -BucketName "$StackName-frontend-$accountId"
            Clear-BucketIfExists -BucketName "$StackName-iot-data-$accountId"
        }

        Write-Host "Deleting failed stack: $StackName"
        aws cloudformation delete-stack `
            --stack-name $StackName `
            --region $Region
        if ($LASTEXITCODE -ne 0) { throw "Failed to start stack deletion" }

        # Wait for deletion to complete.
        Write-Host "Waiting for stack deletion..."
        $maxAttempts = 60
        $attempt = 0
        while ($attempt -lt $maxAttempts) {
            $statusCheck = ""
            try {
                $statusCheck = aws cloudformation describe-stacks `
                    --stack-name $StackName `
                    --region $Region `
                    --query "Stacks[0].StackStatus" `
                    --output text 2>$null
            } catch {
                $statusCheck = ""
            }

            if (-not $statusCheck) {
                Write-Host "Stack deletion complete"
                break
            }

            Start-Sleep -Seconds 2
            $attempt++
        }
    }

    sam build --template-file template.yaml
    if ($LASTEXITCODE -ne 0) { throw "sam build failed" }

    sam deploy `
        --template-file template.yaml `
        --stack-name $StackName `
        --region $Region `
        --resolve-s3 `
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM `
        --no-confirm-changeset `
        --no-fail-on-empty-changeset
    if ($LASTEXITCODE -ne 0) { throw "sam deploy failed" }

    $stackJson = aws cloudformation describe-stacks `
        --stack-name $StackName `
        --region $Region `
        --query "Stacks[0].Outputs" `
        --output json | ConvertFrom-Json

    $apiUrl = ($stackJson | Where-Object OutputKey -eq 'ApiUrl').OutputValue
    $frontendBucket = ($stackJson | Where-Object OutputKey -eq 'FrontendBucketName').OutputValue

    if (-not $apiUrl -or -not $frontendBucket) {
        throw "Failed to read stack outputs for ApiUrl or FrontendBucketName."
    }

    $apiBaseUrl = $apiUrl.TrimEnd('/')

    $configPath = Join-Path $frontendRoot "config.js"
    Set-Content -Path $configPath -Value "window.IOT_API_BASE_URL = '$apiBaseUrl';"

    $espEndpointPath = Join-Path $espRoot "cloud_endpoint.h"
    $espHeader = @"
#ifndef CLOUD_API_BASE_URL
#define CLOUD_API_BASE_URL "$apiBaseUrl"
#endif
"@
    Set-Content -Path $espEndpointPath -Value $espHeader

    aws s3 sync $frontendRoot "s3://$frontendBucket" --delete
    if ($LASTEXITCODE -ne 0) { throw "frontend sync failed" }

    # Smoke check: API health + sample ingestion.
    $health = Invoke-RestMethod -Uri "$apiBaseUrl/health" -Method Get
    if ($health.status -ne "ok") {
        throw "Cloud health check failed"
    }

    $samplePayload = @{
        node_id = "NODE_TH"
        sensor_id = "SENSOR-TH-01"
        metrics = @{
            temperature = 28.5
            humidity = 61.2
        }
    } | ConvertTo-Json

    $samplePost = Invoke-RestMethod -Uri "$apiBaseUrl/data" -Method Post -ContentType "application/json" -Body $samplePayload
    if (-not $samplePost.data_id) {
        throw "Cloud data ingestion smoke check failed"
    }

    Write-Host "Frontend deployed to: s3://$frontendBucket"
    Write-Host "API URL: $apiBaseUrl"
    Write-Host "ESP8266 endpoint header generated: $espEndpointPath"
    Write-Host "Cloud ingestion smoke test data_id: $($samplePost.data_id)"
} finally {
    Pop-Location
}