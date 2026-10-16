@echo off
REM RetroBuddy setup 1.3-1.4: create the venv (Python 3.13) and install dependencies.
REM Writes results to logs\setup_env.log. Safe to re-run.
cd /d "%~dp0"
if not exist logs mkdir logs
set LOG=logs\setup_env.log
echo === RetroBuddy setup 1.3-1.4 === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
echo. >> "%LOG%"

echo [1.3 create venv with py -3.13] >> "%LOG%"
if exist .venv\Scripts\python.exe (
  echo venv already exists, skipping creation >> "%LOG%"
) else (
  py -3.13 -m venv .venv >> "%LOG%" 2>&1
)
if not exist .venv\Scripts\python.exe (
  echo FAILED: .venv\Scripts\python.exe not found after venv creation >> "%LOG%"
  echo === done with errors === >> "%LOG%"
  exit
)
echo venv python: >> "%LOG%"
.venv\Scripts\python.exe --version >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo [1.4 upgrade pip] >> "%LOG%"
.venv\Scripts\python.exe -m pip install --upgrade pip >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo [1.4 install pyboy anthropic python-dotenv] >> "%LOG%"
.venv\Scripts\python.exe -m pip install pyboy anthropic python-dotenv >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo [1.4 verify imports] >> "%LOG%"
.venv\Scripts\python.exe -c "import pyboy, anthropic, dotenv; print('pyboy', pyboy.__version__); print('anthropic', anthropic.__version__); print('dotenv ok')" >> "%LOG%" 2>&1
echo. >> "%LOG%"

echo [.env present?] >> "%LOG%"
if exist .env (echo yes >> "%LOG%") else (echo no >> "%LOG%")
echo. >> "%LOG%"
echo === done === >> "%LOG%"
exit
