@echo off
REM Step 7: open the RetroBuddy text chat in this window (dev state with a starter). Transcript also in logs\session.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
.venv\Scripts\python.exe -m retrobuddy.cli --state saves\dev_starter.state --speed 1
echo.
echo (session ended; press any key to close)
pause >nul
