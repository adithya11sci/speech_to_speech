# PowerShell script to start the backend agent

Write-Host "=== Starting Avatar Gen Backend ===" -ForegroundColor Cyan
Write-Host "Make sure LiveKit server is running first!" -ForegroundColor Yellow
Write-Host ""

Set-Location "$PSScriptRoot\backend"
python agent.py dev
