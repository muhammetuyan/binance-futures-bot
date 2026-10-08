param([switch]$Quiet)
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$tailscalePath = Join-Path $env:ProgramFiles "Tailscale\tailscale.exe"
if (-not (Test-Path -LiteralPath $tailscalePath)) {
    if (-not $Quiet) { Write-Host "Tailscale kurulu değil. Önce resmi Tailscale uygulamasını kurun." }
    return
}
$network = (& $tailscalePath status --json | ConvertFrom-Json)
if ($network.BackendState -ne "Running") {
    if (-not $Quiet) { Write-Host "Tailscale'de giriş yapın ve bu kısayolu yeniden açın." }
    return
}
$remoteHost = $network.Self.DNSName.TrimEnd('.')
$serve = (& $tailscalePath serve status --json | ConvertFrom-Json)
$existing443 = $serve.TCP.'443'
if ($null -ne $existing443) {
    $target = $serve.Web."${remoteHost}:443".Handlers.'/'.Proxy
    if ($target -ne 'http://127.0.0.1:3000') {
        throw "443 üzerinde başka bir Tailscale servisi var; mevcut ayarlar değiştirilmedi."
    }
} else {
    if ($Quiet) {
        # Do not block normal startup on a first-time account permission prompt.
        return
    }
    & $tailscalePath serve --bg --https=443 http://127.0.0.1:3000
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$runtimeDir = Join-Path $projectRoot 'runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
@{url="https://$remoteHost"; state="private"} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $runtimeDir 'remote_access.json')
if (-not $Quiet) {
    Write-Host "Telefon bağlantısı: https://$remoteHost"
    Write-Host "Telefonda Tailscale'i bu cihaza erişim izni olan aynı tailnet'e bağlayın."
    Write-Host "Bu tailnet'teki yetkili kullanıcılar dashboard'u kontrol edebilir; yalnızca güvendiğiniz kişileri davet edin."
}
