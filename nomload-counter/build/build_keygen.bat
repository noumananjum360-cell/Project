@echo off
REM Builds the vendor licence key generator (dist\NomLoadKeygen.exe). Never give this to customers.
setlocal
cd /d "%~dp0\.."
if not exist ".venv-build\Scripts\python.exe" (
  echo Run build\build_windows.bat first.
  pause
  exit /b 1
)
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --workpath build\work-keygen --distpath dist build\keygen.spec
if errorlevel 1 ( echo BUILD FAILED & pause & exit /b 1 )
echo Done: dist\NomLoadKeygen.exe
pause
