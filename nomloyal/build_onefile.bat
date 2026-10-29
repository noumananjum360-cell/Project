@echo off
rem Optional single-file NomLoyal.exe (starts slower than the folder build). Run build.bat first.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo Run build.bat first. & pause & exit /b 1 )
".venv\Scripts\python.exe" -m PyInstaller main.py --onefile --windowed --name NomLoyal-portable ^
  --icon assets\brand\app.ico --add-data "assets;assets" --add-data "templates;templates" ^
  --hidden-import PySide6.QtSvg --hidden-import PySide6.QtPrintSupport --hidden-import qrcode.image.svg --noconfirm
if errorlevel 1 ( echo Build failed. & pause & exit /b 1 )
echo Done: dist\NomLoyal-portable.exe
pause
