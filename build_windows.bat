@echo off
rem Builds "Sonicu Serial Monitor.exe" into dist\.
rem Run on a Windows PC with Python 3 installed (https://www.python.org/downloads/).
rem Also used by the GitHub release workflow (CI is set there, so it doesn't pause).
cd /d "%~dp0"

py -3 -m venv .venv-build 2>nul || python -m venv .venv-build
if errorlevel 1 (
    echo Python 3 is required: https://www.python.org/downloads/
    goto :fail
)
.venv-build\Scripts\python -m pip install -q --upgrade pip || goto :fail
.venv-build\Scripts\python -m pip install -q -r requirements.txt pyinstaller || goto :fail
.venv-build\Scripts\pyinstaller --onefile --console --noconfirm --name "Sonicu Serial Monitor" ^
    --distpath dist\windows --workpath build\windows --specpath build\windows ^
    serial_monitor.py || goto :fail

echo.
echo Built: dist\windows\Sonicu Serial Monitor.exe
if not defined CI pause
exit /b 0

:fail
echo Build failed.
if not defined CI pause
exit /b 1
