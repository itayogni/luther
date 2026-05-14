Set-Location 'C:\Users\ItayOgni\Documents\vc\עוזר אישי שלי\luther\core'
$env:LUTHER_DATABASE_URL = 'sqlite+aiosqlite:///luther_dev.db'
C:\luther-venv\Scripts\pip.exe install -e . -q 2>$null
C:\luther-venv\Scripts\uvicorn.exe luther.main:app --host 0.0.0.0 --port 8000 --reload
