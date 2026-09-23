@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo Engineer AI - Windows EXE Build
echo ==========================================

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m PyInstaller ^
  --onefile ^
  --noconsole ^
  --clean ^
  --name EngineerAI ^
  --collect-all uvicorn ^
  --collect-all fastapi ^
  main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED.
    pause
    exit /b 1
)

echo.
echo BUILD COMPLETE:
echo %CD%\dist\EngineerAI.exe
pause
