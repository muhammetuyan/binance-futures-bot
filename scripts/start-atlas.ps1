param(
  [switch]$NoBrowser,
  [switch]$KeepPaused
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $projectRoot "runtime"
$pidFile = Join-Path $runtimeDir "processes.json"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$tailscalePath = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
if (Test-Path -LiteralPath $tailscalePath) {
    try {
        $network = (& $tailscalePath status --json | ConvertFrom-Json)
        if ($network.BackendState -eq 'Running') { $env:ATLAS_REMOTE_HOST = $network.Self.DNSName.TrimEnd('.') }
        & (Join-Path $PSScriptRoot 'connect-phone.ps1') -Quiet
    } catch { Write-Warning "Telefon bağlantısı kontrol edilemedi; yerel bot başlatılacak." }
}

function Test-AtlasProcess {
    param([int]$ProcessId, [string]$Needle)
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    return $null -ne $processInfo -and $processInfo.CommandLine -like "*$Needle*"
}

function Get-AtlasPortOwner {
    param([int]$Port, [string]$Needle)
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $listener) { return $null }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
    if ($null -ne $processInfo -and $processInfo.CommandLine -like "*$Needle*") { return $processInfo }
    throw "$Port numaralı bağlantı noktası başka bir program tarafından kullanılıyor."
}

function Resume-Atlas {
    Invoke-WebRequest -UseBasicParsing -Method Post -ContentType "application/json" "http://127.0.0.1:8788/api/control/resume" -TimeoutSec 3 | Out-Null
}

$existingBackend = Get-AtlasPortOwner -Port 8788 -Needle "bot.service"
$existingDashboard = Get-AtlasPortOwner -Port 3000 -Needle "$projectRoot"
if (($null -eq $existingBackend) -xor ($null -eq $existingDashboard)) {
    throw "Atlas Trade'ın yalnızca bir parçası çalışıyor. Önce Durdur kısayolunu kullanın."
}
if ($null -ne $existingBackend -and $null -ne $existingDashboard) {
    @{
        backend = $existingBackend.ProcessId
        dashboard = $existingDashboard.ProcessId
        project = $projectRoot
    } | ConvertTo-Json | Set-Content -Encoding UTF8 $pidFile
    if (-not $KeepPaused) { Resume-Atlas }
    if (-not $NoBrowser) { Start-Process "http://localhost:3000/" }
    exit 0
}

$backendOut = Join-Path $runtimeDir "backend.out.log"
$backendErr = Join-Path $runtimeDir "backend.err.log"
$dashboardOut = Join-Path $runtimeDir "dashboard.out.log"
$dashboardErr = Join-Path $runtimeDir "dashboard.err.log"

$backend = Start-Process -FilePath "python.exe" -ArgumentList "-m", "bot.service" -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr -PassThru
$dashboard = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $dashboardOut -RedirectStandardError $dashboardErr -PassThru

$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        $dashboardResponse = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:3000/" -TimeoutSec 10
        $healthResponse = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8788/api/health" -TimeoutSec 2
        if ($dashboardResponse.StatusCode -eq 200 -and $healthResponse.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 750
    }
}

if (-not $ready) {
    Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $dashboard.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Atlas Trade başlatılamadı. runtime klasöründeki logları kontrol edin." -ForegroundColor Red
    Read-Host "Kapatmak için Enter"
    exit 1
}

$runningBackend = Get-AtlasPortOwner -Port 8788 -Needle "bot.service"
$runningDashboard = Get-AtlasPortOwner -Port 3000 -Needle "$projectRoot"
@{
    backend = $runningBackend.ProcessId
    dashboard = $runningDashboard.ProcessId
    project = $projectRoot
} | ConvertTo-Json | Set-Content -Encoding UTF8 $pidFile
if (-not $KeepPaused) { Resume-Atlas }

if (-not $NoBrowser) {
  Start-Process "http://localhost:3000/"
}
