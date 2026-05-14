param()

$LutherRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$CoreDir    = Join-Path $LutherRoot "core"
$GatewayDir = Join-Path $LutherRoot "gateway"
$LockFile   = Join-Path $GatewayDir "auth_info\session\lockfile"

Write-Host "=== Luther Startup ===" -ForegroundColor Cyan

# 1. Kill only Node processes (gateway). Node will clean up its own Puppeteer Chrome children.
#    We deliberately do NOT kill all chrome.exe — that would close the user's browser!
$nodeProcs = Get-Process -Name "node" -ErrorAction SilentlyContinue
if ($nodeProcs) {
    Write-Host "Stopping $($nodeProcs.Count) Node process(es) (gateway)..." -ForegroundColor Yellow
    $nodeProcs | Stop-Process -Force
    Start-Sleep -Milliseconds 1500
}

# 2. Remove lockfile if it exists
if (Test-Path $LockFile) {
    Remove-Item $LockFile -Force
    Write-Host "Removed stale lockfile." -ForegroundColor Green
}

# 3. Free port 8000 if occupied
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($conn) {
    $pid8000 = $conn.OwningProcess | Select-Object -First 1
    if ($pid8000) {
        Write-Host "Freeing port 8000 (PID $pid8000)..." -ForegroundColor Yellow
        Stop-Process -Id $pid8000 -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}

# 4. Write helper scripts so Start-Process can call them cleanly
$backendScript = Join-Path $LutherRoot "run_backend.ps1"
Set-Content -Path $backendScript -Value @"
Set-Location '$CoreDir'
`$env:LUTHER_DATABASE_URL = 'sqlite+aiosqlite:///luther_dev.db'
Write-Host '--- Luther Core (FastAPI :8000) ---' -ForegroundColor Cyan
C:\luther-venv\Scripts\pip.exe install -e . -q 2>`$null
C:\luther-venv\Scripts\uvicorn.exe luther.main:app --host 0.0.0.0 --port 8000 --reload
"@ -Encoding UTF8

$gatewayScript = Join-Path $LutherRoot "run_gateway.ps1"
Set-Content -Path $gatewayScript -Value @"
Set-Location 'C:\luther-gateway'
Write-Host '--- Luther Gateway (WhatsApp) ---' -ForegroundColor Green
npm run dev
"@ -Encoding UTF8

# 5. Launch both in new windows
Write-Host "Starting Luther Core..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -File `"$backendScript`""

Start-Sleep -Seconds 3

Write-Host "Starting Luther Gateway..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -File `"$gatewayScript`""

Write-Host ""
Write-Host "Both services launched in separate windows." -ForegroundColor Green
Write-Host "1. Wait for Gateway to show QR (or 'connected')"
Write-Host "2. Send yourself a WhatsApp message"
Write-Host "3. Luther should reply: received: <your message>"
Write-Host ""
