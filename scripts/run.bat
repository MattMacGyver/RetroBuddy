@echo off
REM Generic runner: scripts\run.bat <module-or-script> [args]. Writes logs\run.log.
REM Example (from a shortcut or another bat): scripts\run.bat tools\make_savestate.py
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\run.log
echo === run %* === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
.venv\Scripts\python.exe %* >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"
echo === done === >> "%LOG%"
exit
