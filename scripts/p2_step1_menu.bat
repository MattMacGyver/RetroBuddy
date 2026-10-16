@echo off
REM Plan 2 step 1: menu extraction check. Writes logs\p2_step1.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\p2_step1.log
echo === plan 2 step 1: menus === > "%LOG%"
.venv\Scripts\python.exe tools\check_menu.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo === done === >> "%LOG%"
exit
