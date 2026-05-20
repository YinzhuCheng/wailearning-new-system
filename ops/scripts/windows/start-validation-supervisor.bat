@echo off
setlocal
set "REPO_ROOT=%~dp0..\..\.."
set "STATE_DIR=%REPO_ROOT%\.agent-run\validation-daemon"
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%"
set "ARGS_FILE=%STATE_DIR%\WAI-VALID-supervisor-args.json"
"%REPO_ROOT%\.venv\Scripts\python.exe" "%REPO_ROOT%\ops\scripts\dev\wai_valid_capture_args.py" "%ARGS_FILE%" %*
if errorlevel 1 exit /b %errorlevel%
"%REPO_ROOT%\.venv\Scripts\python.exe" "%REPO_ROOT%\ops\scripts\dev\wai_valid_windows_launcher.py" supervisor --args-file "%ARGS_FILE%"
endlocal
