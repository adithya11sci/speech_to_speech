# PowerShell script to start LiveKit server

$LIVEKIT_DIR = "$PSScriptRoot\livekit-server"
$LIVEKIT_EXE = "$LIVEKIT_DIR\livekit-server.exe"
$CONFIG_FILE = "$LIVEKIT_DIR\config.yaml"

if (-not (Test-Path $LIVEKIT_EXE)) {
    Write-Host "✗ LiveKit server not found!" -ForegroundColor Red
    Write-Host "Please run setup_livekit.ps1 first" -ForegroundColor Yellow
    exit 1
}

Write-Host "=== Starting LiveKit Server ===" -ForegroundColor Cyan
Write-Host "Server will be available at: ws://localhost:7880" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

& $LIVEKIT_EXE --config $CONFIG_FILE --dev
