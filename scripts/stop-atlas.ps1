$ErrorActionPreference = "SilentlyContinue"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $projectRoot "runtime"
$pidFile = Join-Path $runtimeDir "processes.json"

function Stop-AtlasPortOwner {
    param([int]$Port, [string]$Needle)
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($null -ne $processInfo -and $processInfo.CommandLine -like "*$Needle*") {
            Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    Invoke-WebRequest -UseBasicParsing -Method Post -ContentType "application/json" "http://127.0.0.1:8788/api/control/pause" -TimeoutSec 3 | Out-Null
} catch {
}

# Başlatıcı PID değişse bile gerçek dinleyici süreçlerini güvenli biçimde bulup kapat.
Stop-AtlasPortOwner -Port 8788 -Needle "bot.service"
Stop-AtlasPortOwner -Port 3000 -Needle $projectRoot

if (Test-Path $pidFile) {
    $saved = Get-Content -Raw $pidFile | ConvertFrom-Json
    if ($saved.project -eq $projectRoot) {
        $backend = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.backend)" -ErrorAction SilentlyContinue
        $dashboard = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.dashboard)" -ErrorAction SilentlyContinue
        if ($null -ne $backend -and $backend.CommandLine -like "*bot.service*") {
            Stop-Process -Id $backend.ProcessId -Force
        }
        if ($null -ne $dashboard -and $dashboard.CommandLine -like "*$projectRoot*") {
            Stop-Process -Id $dashboard.ProcessId -Force
        }
    }
    Remove-Item -LiteralPath $pidFile -Force
}

Write-Host "Atlas Trade durduruldu. Borsadaki mevcut stop/kâr emirleri korunur." -ForegroundColor Green
Start-Sleep -Seconds 2
