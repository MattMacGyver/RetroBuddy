@echo off
REM Step 6b: walk bedroom -> Viridian City on the dev state with the AVOID policy (routes around grass). Writes logs\step6b.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\step6b.log
echo === step 6b: avoid policy === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
.venv\Scripts\python.exe -m retrobuddy.pilot --to "Viridian City" --window --speed 1 --policy avoid --state saves\dev_starter.state >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo === done === >> "%LOG%"
exit
