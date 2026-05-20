@echo off
setlocal
set "REPO_ROOT=%~dp0..\..\.."
set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
set "STATE_DIR=%REPO_ROOT%\.agent-run\validation-daemon"
if not exist "%STATE_DIR%" mkdir "%STATE_DIR%"

set "RUN_ID=%~1"
if "%RUN_ID%"=="" set "RUN_ID=custom-samples"
set "BLOCK_NAME=%~2"
if "%BLOCK_NAME%"=="" set "BLOCK_NAME=custom-samples"
set "SAMPLES_FILE=%~3"
if "%SAMPLES_FILE%"=="" (
  echo Usage: start-custom-validation-block.bat ^<run-id^> ^<block-name^> ^<samples-file^> [max-runtime-seconds] [concurrency] [regression-mode] 1>&2
  exit /b 2
)
set "MAX_RUNTIME_SECONDS=%~4"
if "%MAX_RUNTIME_SECONDS%"=="" set "MAX_RUNTIME_SECONDS=10800"
set "CONCURRENCY=%~5"
if "%CONCURRENCY%"=="" set "CONCURRENCY=10"
set "REGRESSION_MODE=%~6"
if "%REGRESSION_MODE%"=="" set "REGRESSION_MODE=light"

set "ARGS_JSON=%STATE_DIR%\WAI-VALID-%RUN_ID%-custom-args.json"
"%PYTHON_EXE%" "%REPO_ROOT%\ops\scripts\dev\wai_valid_build_custom_args.py" ^
  --run-id "%RUN_ID%" ^
  --block "%BLOCK_NAME%" ^
  --samples-file "%SAMPLES_FILE%" ^
  --concurrency "%CONCURRENCY%" ^
  --regression-mode "%REGRESSION_MODE%" ^
  --output-json "%ARGS_JSON%"
if errorlevel 1 exit /b %errorlevel%

call "%REPO_ROOT%\ops\scripts\windows\start-validation-supervisor.bat" --args-file "%ARGS_JSON%" --process-tag "WAI-VALID-%RUN_ID%" --max-runtime-seconds "%MAX_RUNTIME_SECONDS%"
if errorlevel 1 exit /b %errorlevel%

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\ops\scripts\windows\start-validation-monitor-detached.ps1" "%RUN_ID%"
endlocal
