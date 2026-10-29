@echo off
REM ==================================================================
REM  NomLoad Counter - Windows build
REM  venv -> tests -> PyInstaller -> self-test -> Inno Setup installer
REM  Double-click this file, or run it from a Command Prompt.
REM  Needs: Python 3.11 (64-bit) and Inno Setup 6.
REM ==================================================================
setlocal EnableExtensions
title NomLoad Counter - build
cd /d "%~dp0\.."
echo.
echo  NomLoad Counter - Windows build
echo  Project folder: %CD%
echo.

REM ---------- find Python 3.11 ----------
set "PY="
where py >nul 2>nul && (py -3.11 -c "import sys" >nul 2>nul && set "PY=py -3.11")
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python was not found.
  echo         Install Python 3.11 64-bit from https://www.python.org/downloads/
  echo         and tick "Add python.exe to PATH" during setup.
  goto :fail
)
%PY% -c "import sys; assert sys.version_info[:2] >= (3, 10), sys.version" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required. Found:
  %PY% --version
  goto :fail
)
echo Using: & %PY% --version

REM ---------- virtual environment ----------
if not exist ".venv-build\Scripts\python.exe" (
  echo.
  echo === Creating build environment (.venv-build) ===
  %PY% -m venv .venv-build
  if errorlevel 1 goto :fail
)
set "VPY=%CD%\.venv-build\Scripts\python.exe"
echo.
echo === Installing packages (first time takes a few minutes) ===
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements-dev.txt
if errorlevel 1 (
  echo [ERROR] Package installation failed. Check your internet connection and try again.
  goto :fail
)

REM ---------- licensing key pair ----------
if not exist "nomload\licensing\vendor_public_key.pem" (
  echo.
  echo  No vendor public key in nomload\licensing\vendor_public_key.pem
  echo  A build needs the public key that matches YOUR licence keys.
  echo   - If you already have licence keys: copy the project zip that came with them,
  echo     or copy vendor_public_key.pem into nomload\licensing\ and run this again.
  echo   - Creating a NEW key pair makes all existing licence keys invalid for this build.
  echo.
  choice /C YN /M "Create a NEW licensing key pair now"
  if errorlevel 2 goto :fail
  echo.
  echo === Creating your licensing key pair ===
  "%VPY%" tools\keygen.py init
  if errorlevel 1 goto :fail
  echo.
  echo  IMPORTANT: back up tools\vendor_keys\vendor_private.pem somewhere safe.
  echo  You need it to generate licence keys for customers. Never share it.
  echo.
)

REM ---------- assets, models, samples ----------
echo.
echo === Preparing assets ===
"%VPY%" tools\make_assets.py
if errorlevel 1 goto :fail
if not exist "models\starter_detector.onnx" (
  echo Starter model missing - training it now (about 1 hour^)...
  "%VPY%" tools\train_starter.py
  if errorlevel 1 goto :fail
)
if not exist "samples\answer_key.csv" (
  "%VPY%" tools\generate_samples.py
  if errorlevel 1 goto :fail
)

REM ---------- tests ----------
echo.
echo === Running tests ===
"%VPY%" -m pytest -q tests
if errorlevel 1 (
  echo [ERROR] Tests failed - see above.
  goto :fail
)

REM ---------- PyInstaller ----------
echo.
echo === Building NomLoad.exe (PyInstaller) ===
if exist build\work rmdir /s /q build\work
if exist dist\NomLoad rmdir /s /q dist\NomLoad
"%VPY%" -m PyInstaller --noconfirm --workpath build\work --distpath dist build\nomload.spec
if errorlevel 1 goto :fail

REM ---------- self-test ----------
echo.
echo === Self-test of the packaged program (1-3 minutes) ===
"dist\NomLoad\NomLoad.exe" --selftest --report "dist\selftest_report.txt"
set "RC=%ERRORLEVEL%"
if exist "dist\selftest_report.txt" type "dist\selftest_report.txt"
if not "%RC%"=="0" (
  echo [ERROR] Self-test failed - installer not built.
  goto :fail
)

REM ---------- Inno Setup ----------
echo.
echo === Building installer (Inno Setup) ===
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo [WARNING] Inno Setup 6 is not installed, so no setup.exe was made.
  echo           The program itself is ready in: %CD%\dist\NomLoad\NomLoad.exe
  echo           Install Inno Setup 6 from https://jrsoftware.org/isinfo.php and run this again.
  goto :done
)
"%ISCC%" build\installer.iss
if errorlevel 1 goto :fail
echo.
echo ==================================================================
echo  SUCCESS
echo  Installer: %CD%\dist\installer\NomLoadCounter_Setup_1.0.0.exe
echo  Program  : %CD%\dist\NomLoad\NomLoad.exe
echo ==================================================================
goto :done

:fail
echo.
echo ==================================================================
echo  BUILD FAILED - read the messages above.
echo ==================================================================
echo.
pause
endlocal
exit /b 1

:done
echo.
pause
endlocal
exit /b 0
