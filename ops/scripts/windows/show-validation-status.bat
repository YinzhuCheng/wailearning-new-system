@echo off
setlocal
set "REPO_ROOT=%~dp0..\..\.."
set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
set "STATUS_SCRIPT=%REPO_ROOT%\ops\scripts\dev\wai_valid_status.py"

if not exist "%PYTHON_EXE%" (
  echo Missing repository venv interpreter: "%PYTHON_EXE%" 1>&2
  exit /b 2
)

if not exist "%STATUS_SCRIPT%" (
  echo Missing WAI-VALID status script: "%STATUS_SCRIPT%" 1>&2
  exit /b 2
)

"%PYTHON_EXE%" "%STATUS_SCRIPT%" %*
exit /b %ERRORLEVEL%
