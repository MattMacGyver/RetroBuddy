@echo off
REM Step 6: (1) walk bedroom -> Oak's lab on the clean start state; (2) make a dev state with a starter; (3) walk bedroom -> Viridian City on it. Windowed, real time. Writes logs\step6.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\step6.log
echo === step 6: pilot walks === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
echo [walk 1: Oak's lab, clean state] >> "%LOG%"
.venv\Scripts\python.exe -m retrobuddy.pilot --to "Oaks Lab" --window --speed 1 >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo [make dev state] >> "%LOG%"
.venv\Scripts\python.exe tools\make_dev_state.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo [walk 2: Viridian City, dev state] >> "%LOG%"
.venv\Scripts\python.exe -m retrobuddy.pilot --to "Viridian City" --window --speed 1 --state saves\dev_starter.state >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo === done === >> "%LOG%"
exit
