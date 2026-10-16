@echo off
REM RetroBuddy environment check. Writes results to logs\check_env.log.
cd /d "%~dp0"
if not exist logs mkdir logs
set LOG=logs\check_env.log
echo === RetroBuddy environment check === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"
echo [py --version] >> "%LOG%"
py --version >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo [py -0p  (installed Pythons)] >> "%LOG%"
py -0p >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo [python --version] >> "%LOG%"
python --version >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo [git --version] >> "%LOG%"
git --version >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo [venv present?] >> "%LOG%"
if exist .venv\Scripts\python.exe (echo yes >> "%LOG%") else (echo no >> "%LOG%")
echo. >> "%LOG%"
echo [.env present?] >> "%LOG%"
if exist .env (echo yes >> "%LOG%") else (echo no >> "%LOG%")
echo. >> "%LOG%"
echo === done === >> "%LOG%"
exit
