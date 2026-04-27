$ErrorActionPreference = 'Stop'

$health = Invoke-RestMethod -Uri 'http://localhost:5000/health' -Method Get
if ($health.status -ne 'ok') {
    throw 'API health check failed'
}

function Wait-ForSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataId,
        [int]$MaxAttempts = 15
    )

    $attempt = 0
    $summary = $null

    while ($attempt -lt $MaxAttempts) {
        $summary = Invoke-RestMethod -Uri ("http://localhost:5000/summary?id=" + $DataId) -Method Get
        if ($summary.status -eq 'done' -or $summary.status -eq 'failed') {
            return @{
                summary = $summary
                attempts = $attempt
            }
        }
        Start-Sleep -Seconds 1
        $attempt++
    }

    throw "Summary polling failed for data_id=$DataId"
}

$payloadTH = @{
    node_id = 'NODE_TH'
    sensor_id = 'sensor-th-01'
    metrics = @{
        temperature = 27.3
        humidity = 64.1
    }
} | ConvertTo-Json

$payloadPA = @{
    node_id = 'NODE_PA'
    sensor_id = 'sensor-pa-01'
    metrics = @{
        pressure = 1012.8
        ethanol = 21.7
    }
} | ConvertTo-Json

$postTH = Invoke-RestMethod -Uri 'http://localhost:5000/data' -Method Post -ContentType 'application/json' -Body $payloadTH
$postPA = Invoke-RestMethod -Uri 'http://localhost:5000/data' -Method Post -ContentType 'application/json' -Body $payloadPA

if (-not $postTH.data_id) {
    throw 'POST /data for NODE_TH did not return data_id'
}
if (-not $postPA.data_id) {
    throw 'POST /data for NODE_PA did not return data_id'
}

$resultTH = Wait-ForSummary -DataId $postTH.data_id
$resultPA = Wait-ForSummary -DataId $postPA.data_id

"HEALTH=$($health | ConvertTo-Json -Compress)"
"POST_NODE_TH=$($postTH | ConvertTo-Json -Compress)"
"POST_NODE_PA=$($postPA | ConvertTo-Json -Compress)"
"FINAL_SUMMARY_NODE_TH=$($resultTH.summary | ConvertTo-Json -Compress)"
"FINAL_SUMMARY_NODE_PA=$($resultPA.summary | ConvertTo-Json -Compress)"
"ATTEMPTS_NODE_TH=$($resultTH.attempts)"
"ATTEMPTS_NODE_PA=$($resultPA.attempts)"
