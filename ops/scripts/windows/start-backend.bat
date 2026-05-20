@echo off
setlocal
cd /d "%~dp0\..\..\.."

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn apps.backend.courseeval_backend.main:app --host 0.0.0.0 --port 8001 --reload
) else (
  python -m uvicorn apps.backend.courseeval_backend.main:app --host 0.0.0.0 --port 8001 --reload
)
