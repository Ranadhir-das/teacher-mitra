$env:DEBUG = 'True'
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\manage.py" runserver 127.0.0.1:8000
