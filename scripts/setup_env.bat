@echo off
REM Create the venv (Python 3.13) and install requirements. Writes logs\setup_env.log. Safe to re-run.
cd /d "%~dp0\.."
if not exist logs mkdir logs
set LOG=logs\setup_env.log
echo === RetroBuddy setup === > "%LOG%"
echo Run at %DATE% %TIME% >> "%LOG%"
if not exist .venv\Scripts\python.exe py -3.13 -m venv .venv >> "%LOG%" 2>&1
if not exist .venv\Scripts\python.exe (
  echo FAILED: venv not created >> "%LOG%"
  exit
)
.venv\Scripts\python.exe --version >> "%LOG%" 2>&1
.venv\Scripts\python.exe -m pip install --upgrade pip >> "%LOG%" 2>&1
.venv\Scripts\python.exe -m pip install -r requirements.txt >> "%LOG%" 2>&1
.venv\Scripts\python.exe -c "import pyboy, anthropic, dotenv; print('imports ok; anthropic', anthropic.__version__)" >> "%LOG%" 2>&1
echo === done === >> "%LOG%"
exit
