@echo off
setlocal
set "REPO_ROOT=%~dp0..\..\.."
set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
set "STATE_DIR=%REPO_ROOT%\.agent-run\validation-daemon"
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%"

set "RUN_ID=%~1"
if "%RUN_ID%"=="" set "RUN_ID=selector-light-validation"
set "MAX_RUNTIME_SECONDS=%~2"
if "%MAX_RUNTIME_SECONDS%"=="" set "MAX_RUNTIME_SECONDS=10800"
set "CONCURRENCY=%~3"
if "%CONCURRENCY%"=="" set "CONCURRENCY=10"

set "ARGS_JSON=%STATE_DIR%\WAI-VALID-selector-light-args.json"
"%PYTHON_EXE%" "%REPO_ROOT%\ops\scripts\dev\wai_valid_build_selector_light_args.py" ^
  --run-id "%RUN_ID%" ^
  --concurrency "%CONCURRENCY%" ^
  --output-json "%ARGS_JSON%" ^
  --paths ops/scripts/dev/wai_valid_supervisor.py tests/backend/manual/test_validation_selector.py skills/parallel-validation-orchestration/SKILL.md docs/testing/VALIDATION_WORKFLOW_AND_TOOLS.md
if errorlevel 1 exit /b %errorlevel%

call "%REPO_ROOT%\ops\scripts\windows\start-validation-supervisor.bat" --args-file "%ARGS_JSON%" --process-tag "WAI-VALID-%RUN_ID%" --max-runtime-seconds "%MAX_RUNTIME_SECONDS%"
if errorlevel 1 exit /b %errorlevel%

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\ops\scripts\windows\start-validation-monitor-detached.ps1" "%RUN_ID%"
endlocal
