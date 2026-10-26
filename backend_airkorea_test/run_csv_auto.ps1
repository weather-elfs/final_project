param(
    [switch]$Loop,
    [int]$IntervalMinutes = 30
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$asos = "$root\src\collectors\api\data\raw\asos\asos_realtime_pipeline_test.csv"
$air = "$root\backend_airkorea_test\data\airkorea_latest.csv"
$collector = "$root\src\collectors\api\airkorea_collector.py"

if (-not $env:KMA_AUTH_KEY) {
    $env:KMA_AUTH_KEY = Read-Host "KMA API KEY"
}
if (-not $env:AIRKOREA_API_KEY) {
    $env:AIRKOREA_API_KEY = Read-Host "AirKorea API KEY"
}

function Run-Collection {
    Set-Location $root
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $candidate = "$root\backend_airkorea_test\data\airkorea_candidate_$stamp.csv"

    Write-Host "`n=== COLLECTION $stamp ===" -ForegroundColor Cyan

    # ASOS: DRY-RUN ONLY
    Write-Host "[1/3] ASOS"

    $asosBackup = "$asos.before_auto"
    if (Test-Path $asos) {
        Copy-Item $asos $asosBackup -Force
    }

    python -m backend.run_asos_pipeline

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $asos)) {
        Write-Host "[FAIL] ASOS" -ForegroundColor Red
        if (Test-Path $asosBackup) {
            Copy-Item $asosBackup $asos -Force
        }
        return
    }

    Write-Host "[OK] ASOS" -ForegroundColor Green

    # AirKorea: collect to a separate candidate CSV
    Write-Host "[2/3] AirKorea"

    python $collector --realtime --output $candidate

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $candidate)) {
        Write-Host "[FAIL] AirKorea - previous CSV preserved" -ForegroundColor Red
        return
    }

    # Validate all three station codes before replacement

    python -m backend_airkorea_test.validate_airkorea_csv $candidate

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] AirKorea CSV validation" -ForegroundColor Red
        return
    }

    # Preserve previous valid CSV
    if (Test-Path $air) {
        Copy-Item $air "$air.backup_$stamp"
    }

    Copy-Item $candidate $air -Force
    Write-Host "[OK] AirKorea CSV updated" -ForegroundColor Green

    # Read-only API verification
    Write-Host "[3/3] Backend API"

    try {
        $r = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/stations/112/dashboard" -TimeoutSec 15

        Write-Host "OBSERVED_AT:" $r.data.current.observed_at
        Write-Host "PM10:" $r.data.current.pm10_ug_m3
        Write-Host "PM2.5:" $r.data.current.pm25_ug_m3

        $r.data.source_status |
            Format-Table source,status,observed_at,age_minutes -AutoSize
    }
    catch {
        Write-Host "[WARN] API check failed"
    }

    Write-Host "[DONE] No database writes" -ForegroundColor Green
}

if ($Loop) {
    if ($IntervalMinutes -lt 5) {
        throw "Minimum interval is 5 minutes"
    }

    while ($true) {
        try {
            Run-Collection
        }
        catch {
            Write-Host "[ERROR] $_" -ForegroundColor Red
        }

        Write-Host "Next cycle in $IntervalMinutes minutes"
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
}
else {
    Run-Collection
}
