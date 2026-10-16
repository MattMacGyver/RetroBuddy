@echo off
REM Environment check. Writes logs\check_env.log. Safe to re-run.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\check_env.log
echo === RetroBuddy environment check === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
echo [py -0p] >> "%LOG%"
py -0p >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo [git --version] >> "%LOG%"
git --version >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo [venv python] >> "%LOG%"
if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe --version >> "%LOG%" 2>&1) else (echo no venv >> "%LOG%")
echo. >> "%LOG%"
echo [installed packages] >> "%LOG%"
if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe -m pip list >> "%LOG%" 2>&1)
echo. >> "%LOG%"
echo [.env present?] >> "%LOG%"
if exist .env (echo yes >> "%LOG%") else (echo no >> "%LOG%")
echo. >> "%LOG%"
echo [ROM present?] >> "%LOG%"
if exist "ROMs\Pokemon - Red Version.gb" (echo yes >> "%LOG%") else (echo no >> "%LOG%")
echo. >> "%LOG%"
echo [git status] >> "%LOG%"
git status >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo === done === >> "%LOG%"
exit
