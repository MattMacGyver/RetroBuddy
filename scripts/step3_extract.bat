@echo off
REM Step 3: run the extractor check. Writes logs\step3.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\step3.log
echo === step 3: extractor === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
.venv\Scripts\python.exe tools\dump_state.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo === done === >> "%LOG%"
exit
