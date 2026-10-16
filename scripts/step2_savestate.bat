@echo off
REM Step 2: make the start save state (automatic intro) then run the smoke test. Writes logs\step2.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\step2.log
echo === step 2: save state + smoke === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
echo [make_savestate] >> "%LOG%"
.venv\Scripts\python.exe tools\make_savestate.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo. >> "%LOG%"
echo [smoke_emu] >> "%LOG%"
.venv\Scripts\python.exe tools\smoke_emu.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo. >> "%LOG%"
echo === done === >> "%LOG%"
exit
