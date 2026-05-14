Set-Location 'C:\Users\ItayOgni\Documents\vc\עוזר אישי שלי\luther\core'
$env:LUTHER_DATABASE_URL = 'sqlite+aiosqlite:///luther_dev.db'
Write-Host '--- Luther Core (FastAPI :8000) ---' -ForegroundColor Cyan
& .\.venv\Scripts\uvicorn.exe luther.main:app --host 0.0.0.0 --port 8000 --reload
