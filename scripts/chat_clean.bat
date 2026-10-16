@echo off
REM Same as chat.bat but from the clean start state (no starter; Oak will stop you leaving town).
cd /d "%~dp0\.."
if not exist logs mkdir logs
.venv\Scripts\python.exe -m retrobuddy.cli --speed 1
echo.
echo (session ended; press any key to close)
pause >nul
