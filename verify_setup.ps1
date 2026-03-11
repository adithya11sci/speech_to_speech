# PowerShell script to verify Avatar Gen setup

Write-Host "`n=== Avatar Gen Setup Verification ===" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# Check Python
Write-Host "Checking Python..." -NoNewline
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pyVersion = python --version
    Write-Host " ✅ $pyVersion" -ForegroundColor Green
} else {
    Write-Host " ❌ Not found" -ForegroundColor Red
    $allGood = $false
}

# Check Node.js
Write-Host "Checking Node.js..." -NoNewline
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVersion = node --version
    Write-Host " ✅ $nodeVersion" -ForegroundColor Green
} else {
    Write-Host " ❌ Not found" -ForegroundColor Red
    $allGood = $false
}

# Check Python packages
Write-Host "`nChecking Python packages..." -ForegroundColor Yellow
$packages = @("livekit", "livekit-agents", "faster-whisper", "kokoro-onnx", "httpx")
foreach ($pkg in $packages) {
    Write-Host "  $pkg..." -NoNewline
    python -m pip show $pkg 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " ✅" -ForegroundColor Green
    } else {
        Write-Host " ❌" -ForegroundColor Red
        $allGood = $false
    }
}

# Check frontend dependencies
Write-Host "`nChecking frontend dependencies..." -NoNewline
if (Test-Path "$PSScriptRoot\frontend\node_modules") {
    Write-Host " ✅" -ForegroundColor Green
} else {
    Write-Host " ❌ Run 'npm install' in frontend/" -ForegroundColor Red
    $allGood = $false
}

# Check .env file
Write-Host "Checking .env file..." -NoNewline
if (Test-Path "$PSScriptRoot\backend\.env") {
    Write-Host " ✅" -ForegroundColor Green
} else {
    Write-Host " ❌ Not found" -ForegroundColor Red
    $allGood = $false
}

# Check LiveKit server
Write-Host "Checking LiveKit server..." -NoNewline
if (Test-Path "$PSScriptRoot\livekit-server\livekit-server.exe") {
    Write-Host " ✅" -ForegroundColor Green
} else {
    Write-Host " ❌ Run setup_livekit.ps1" -ForegroundColor Red
    $allGood = $false
}

# Check models
Write-Host "`nChecking AI models..." -ForegroundColor Yellow
Write-Host "  Kokoro TTS..." -NoNewline
if ((Test-Path "$PSScriptRoot\backend\models\kokoro\kokoro-v1.0.onnx") -and 
    (Test-Path "$PSScriptRoot\backend\models\kokoro\voices-v1.0.bin")) {
    Write-Host " ✅" -ForegroundColor Green
} else {
    Write-Host " ❌ Missing files" -ForegroundColor Red
    $allGood = $false
}

# Check Python syntax
Write-Host "`nChecking Python code syntax..." -ForegroundColor Yellow
$pyFiles = @("backend\agent.py", "backend\agent\config.py", "backend\agent\asr.py", 
              "backend\agent\llm.py", "backend\agent\tts.py")
foreach ($file in $pyFiles) {
    Write-Host "  $file..." -NoNewline
    python -m py_compile "$PSScriptRoot\$file" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host " ✅" -ForegroundColor Green
    } else {
        Write-Host " ❌" -ForegroundColor Red
        $allGood = $false
    }
}

# Check TypeScript
Write-Host "`nChecking TypeScript..." -NoNewline
Set-Location "$PSScriptRoot\frontend"
npx tsc --noEmit 2>&1 | Out-Null
Set-Location $PSScriptRoot
if ($LASTEXITCODE -eq 0) {
    Write-Host " ✅" -ForegroundColor Green
} else {
    Write-Host " ❌ See errors above" -ForegroundColor Red
    $allGood = $false
}

# Summary
Write-Host "`n" + ("=" * 50) -ForegroundColor Cyan
if ($allGood) {
    Write-Host "✅ All checks passed! Ready to run." -ForegroundColor Green
    Write-Host "`nTo start the system:" -ForegroundColor Yellow
    Write-Host "  1. .\start_livekit.ps1   (in Terminal 1)" -ForegroundColor White
    Write-Host "  2. .\start_backend.ps1   (in Terminal 2)" -ForegroundColor White
    Write-Host "  3. .\start_frontend.ps1  (in Terminal 3)" -ForegroundColor White
} else {
    Write-Host "❌ Some checks failed. Fix the issues above." -ForegroundColor Red
}
Write-Host ("=" * 50) -ForegroundColor Cyan
Write-Host ""
