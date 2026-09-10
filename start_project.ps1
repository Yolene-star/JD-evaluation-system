[CmdletBinding()]
param(
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataRoot = Join-Path $ProjectRoot "data"
$CollectorScript = Join-Path $ProjectRoot "integrations\jd-extraction\collector-server.mjs"

function Test-LocalPort {
    param([Parameter(Mandatory)][int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(700) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Get-ServiceStatus {
    @(
        [pscustomobject]@{ name = "backend"; port = 8001; online = (Test-LocalPort 8001); url = "http://127.0.0.1:8001/api/health" }
        [pscustomobject]@{ name = "frontend"; port = 5192; online = (Test-LocalPort 5192); url = "http://127.0.0.1:5192/" }
        [pscustomobject]@{ name = "jd-collector"; port = 8787; online = (Test-LocalPort 8787); url = "http://localhost:8787/health"; install_url = "http://localhost:8787/install" }
    )
}

function Wait-LocalPort {
    param(
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$Name,
        [int]$Seconds = 30
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-LocalPort $Port) {
            Write-Host "[online] $Name (127.0.0.1:$Port)" -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not start on port $Port within $Seconds seconds."
}

if ($StatusOnly) {
    ConvertTo-Json -InputObject @(Get-ServiceStatus) -Depth 3 -Compress
    exit 0
}

Set-Location -LiteralPath $ProjectRoot
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null

if (Test-LocalPort 8001) {
    Write-Host "[online] Backend already running (127.0.0.1:8001)" -ForegroundColor Green
}
else {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    Start-Process -FilePath $pythonPath `
        -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8001") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $DataRoot "backend.stdout.log") `
        -RedirectStandardError (Join-Path $DataRoot "backend.stderr.log") | Out-Null
    Wait-LocalPort -Port 8001 -Name "Backend"
}

if (Test-LocalPort 8787) {
    Write-Host "[online] JD Collector already running (127.0.0.1:8787)" -ForegroundColor Green
}
else {
    if (-not (Test-Path -LiteralPath $CollectorScript)) {
        throw "Missing JD collector: $CollectorScript"
    }
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    Start-Process -FilePath $nodePath `
        -ArgumentList @($CollectorScript, "--host=127.0.0.1", "--port=8787", "--backend=http://127.0.0.1:8001") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $DataRoot "jd-collector.stdout.log") `
        -RedirectStandardError (Join-Path $DataRoot "jd-collector.stderr.log") | Out-Null
    Wait-LocalPort -Port 8787 -Name "JD Collector"
}

if (Test-LocalPort 5192) {
    Write-Host "[online] Frontend already running (127.0.0.1:5192)" -ForegroundColor Green
}
else {
    $npmPath = (Get-Command npm.cmd -ErrorAction Stop).Source
    Start-Process -FilePath $npmPath `
        -ArgumentList @("--prefix", "frontend", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5192", "--strictPort") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $DataRoot "frontend.stdout.log") `
        -RedirectStandardError (Join-Path $DataRoot "frontend.stderr.log") | Out-Null
    Wait-LocalPort -Port 5192 -Name "Frontend"
}

Write-Host ""
Write-Host "All project services are running:" -ForegroundColor Green
Write-Host "  App:              http://127.0.0.1:5192/"
Write-Host "  Backend:          http://127.0.0.1:8001/api/health"
Write-Host "  Collector health: http://localhost:8787/health"
Write-Host "  Collector setup:  http://localhost:8787/install?project_id=<current-project-id>"
