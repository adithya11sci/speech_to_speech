# PowerShell script to download and setup LiveKit server (no Docker needed)

$LIVEKIT_VERSION = "1.7.2"
$LIVEKIT_DIR = "$PSScriptRoot\livekit-server"
$LIVEKIT_URL = "https://github.com/livekit/livekit/releases/download/v$LIVEKIT_VERSION/livekit_$($LIVEKIT_VERSION)_windows_amd64.zip"

Write-Host "=== LiveKit Server Setup ===" -ForegroundColor Cyan
Write-Host "Downloading LiveKit server v$LIVEKIT_VERSION..." -ForegroundColor Yellow

# Create directory
New-Item -ItemType Directory -Force -Path $LIVEKIT_DIR | Out-Null

# Download LiveKit
$zipFile = "$LIVEKIT_DIR\livekit.zip"
try {
    Write-Host "URL: $LIVEKIT_URL" -ForegroundColor Gray
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $webClient = New-Object System.Net.WebClient
    $webClient.DownloadFile($LIVEKIT_URL, $zipFile)
    Write-Host "Download complete" -ForegroundColor Green
} catch {
    Write-Host "Download failed: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Manual download:" -ForegroundColor Yellow
    Write-Host "1. Download from: $LIVEKIT_URL" -ForegroundColor White
    Write-Host "2. Extract to: $LIVEKIT_DIR" -ForegroundColor White
    exit 1
}

# Extract
Write-Host "Extracting..." -ForegroundColor Yellow
try {
    Expand-Archive -Path $zipFile -DestinationPath $LIVEKIT_DIR -Force
    Remove-Item $zipFile
    Write-Host "Extraction complete" -ForegroundColor Green
} catch {
    Write-Host "Extraction failed: $_" -ForegroundColor Red
    exit 1
}

# Create config file
$configContent = @"
port: 7880
rtc:
  port_range_start: 50000
  port_range_end: 60000
  use_external_ip: false
keys:
  devkey: secret
"@

Set-Content -Path "$LIVEKIT_DIR\config.yaml" -Value $configContent
Write-Host "Configuration created" -ForegroundColor Green

Write-Host ""
Write-Host "=== Setup Complete! ===" -ForegroundColor Cyan
Write-Host "To start LiveKit server, run: .\start_livekit.ps1" -ForegroundColor Yellow
