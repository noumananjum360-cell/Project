@echo off
REM ==================================================================
REM  NomLoad Counter - Windows build: venv -> PyInstaller -> self-test -> Inno Setup
REM  Run from a normal Command Prompt:   build\build_windows.bat
REM  Requires: Python 3.11 x64 on PATH, Inno Setup 6 installed.
REM ==================================================================
setlocal
cd /d "%~dp0\.."

if not exist nomload\licensing\vendor_public_key.pem (
  echo.
  echo  No vendor public key found. Create your licensing key pair ONCE with:
  echo      python tools\keygen.py init
  echo  and keep tools\vendor_keys\vendor_private.pem safe and secret.
  exit /b 1
)

if not exist .venv-build (
  python -m venv .venv-build || exit /b 1
)
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements-dev.txt || exit /b 1

echo === Unit tests ===
python -m pytest -q tests || exit /b 1

echo === Assets ===
python tools\make_assets.py || exit /b 1
if not exist models\starter_detector.onnx (
  echo Starter model missing - training it now (about 1 hour^)...
  python tools\train_starter.py || exit /b 1
)
if not exist samples\answer_key.csv python tools\generate_samples.py

echo === PyInstaller ===
rmdir /s /q build\work 2>nul
pyinstaller --noconfirm --workpath build\work --distpath dist build\nomload.spec || exit /b 1

echo === Self-test of the packaged exe ===
dist\NomLoad\NomLoad.exe --selftest --report dist\selftest_report.txt
set RC=%ERRORLEVEL%
type dist\selftest_report.txt
if not "%RC%"=="0" (
  echo SELF-TEST FAILED - installer not built.
  exit /b 1
)

echo === Inno Setup ===
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo Inno Setup 6 not found. Install it from https://jrsoftware.org/isinfo.php and re-run.
  exit /b 1
)
%ISCC% build\installer.iss || exit /b 1

echo.
echo Done:  dist\installer\NomLoadCounter_Setup_1.0.0.exe
endlocal
