# PowerShell script to start the frontend

Write-Host "=== Starting Avatar Gen Frontend ===" -ForegroundColor Cyan
Write-Host ""

Set-Location "$PSScriptRoot\frontend"
npm run dev
