@echo off
if not defined RB_MIN (set RB_MIN=1 & start "" /min cmd /c "%~f0" & exit)
REM Plan 2 step 3: heal_at_center check. Writes logs\p2_step3.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
set LOG=logs\p2_step3_%RANDOM%.log
echo === plan 2 step 3: heal === > "%LOG%"
.venv\Scripts\python.exe tools\check_heal.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo === done === >> "%LOG%"
exit
