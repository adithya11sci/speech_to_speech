# Complete Setup Script - Run this once to set everything up

Write-Host "=== Avatar Gen Complete Setup ===" -ForegroundColor Cyan
Write-Host ""

# 1. Setup LiveKit
Write-Host "[1/3] Setting up LiveKit server..." -ForegroundColor Yellow
& "$PSScriptRoot\setup_livekit.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ LiveKit setup failed" -ForegroundColor Red
    exit 1
}

# 2. Install Python dependencies
Write-Host "`n[2/3] Installing Python dependencies..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\backend"
pip install -r agent/requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Python dependencies installation failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python dependencies installed" -ForegroundColor Green

# 3. Install Node.js dependencies
Write-Host "`n[3/3] Installing Node.js dependencies..." -ForegroundColor Yellow
Set-Location "$PSScriptRoot\frontend"
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Node.js dependencies installation failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Node.js dependencies installed" -ForegroundColor Green

Write-Host ""
Write-Host "=== Setup Complete! ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "To run the application:" -ForegroundColor Yellow
Write-Host '  1. Terminal 1: .\start_livekit.ps1' -ForegroundColor White
Write-Host '  2. Terminal 2: .\start_backend.ps1' -ForegroundColor White
Write-Host '  3. Terminal 3: .\start_frontend.ps1' -ForegroundColor White
Write-Host ""
Write-Host "Then open http://localhost:5173 in your browser" -ForegroundColor Green
