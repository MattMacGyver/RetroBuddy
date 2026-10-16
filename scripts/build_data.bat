@echo off
REM Rebuild data\maps.json and data\tilesets.json from pokered (clones it into data\pokered if missing). Writes logs\build_data.log.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\build_data.log
echo === build_data === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
.venv\Scripts\python.exe tools\build_data.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
.venv\Scripts\python.exe tools\check_data.py >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo === done === >> "%LOG%"
exit
