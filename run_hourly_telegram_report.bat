@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

if not exist "%PROJECT_DIR%logs" mkdir "%PROJECT_DIR%logs"

set "LOG_FILE=%PROJECT_DIR%logs\telegram_hourly.log"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=%PROJECT_DIR%venv\Scripts\python.exe"
)

>>"%LOG_FILE%" echo.
>>"%LOG_FILE%" echo ==== Started: %date% %time% ====

if not exist "%PYTHON_EXE%" (
    >>"%LOG_FILE%" echo ERROR: Python executable not found.
    >>"%LOG_FILE%" echo Checked .venv\Scripts\python.exe and venv\Scripts\python.exe
    >>"%LOG_FILE%" echo ==== Exit code: 9009 ====
    exit /b 9009
)

if not exist "%PROJECT_DIR%send_market_report_to_telegram.py" (
    >>"%LOG_FILE%" echo ERROR: send_market_report_to_telegram.py not found.
    >>"%LOG_FILE%" echo ==== Exit code: 2 ====
    exit /b 2
)

if not exist "%PROJECT_DIR%.env" (
    >>"%LOG_FILE%" echo ERROR: .env was not found.
    >>"%LOG_FILE%" echo ==== Exit code: 2 ====
    exit /b 2
)

"%PYTHON_EXE%" -u "%PROJECT_DIR%send_market_report_to_telegram.py" >>"%LOG_FILE%" 2>&1

set "EXITCODE=%ERRORLEVEL%"

>>"%LOG_FILE%" echo ==== Exit code: %EXITCODE% ====

exit /b %EXITCODE%