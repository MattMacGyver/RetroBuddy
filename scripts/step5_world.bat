@echo off
REM Step 5: routing check (no ROM needed). Writes logs\step5.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\step5.log
echo === step 5: world === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
.venv\Scripts\python.exe tools\check_world.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo === done === >> "%LOG%"
exit
