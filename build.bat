@echo off
setlocal

python -m PyInstaller --onefile --name EngineerAI --clean main.py

echo.
echo Build complete: dist\\EngineerAI.exe
pause
