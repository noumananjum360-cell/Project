@echo off
setlocal EnableExtensions
title NomLoyal - build Windows app
cd /d "%~dp0"
echo.
echo  ==============================================
echo    NomLoyal - one-click Windows build
echo  ==============================================
echo  Project folder: %CD%
echo  Your data (customers, sales) is in %%LOCALAPPDATA%%\Devnom\NomLoyal and is NOT touched.
echo.

rem ---- 1. find Python 3.11+ ------------------------------------------------
set "PY="
for %%V in (3.12 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,12) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo  [X] Python 3.11 or 3.12 was not found (the pinned Qt version needs one of these).
  echo      Install Python 3.11 or 3.12 from https://www.python.org/downloads/windows/
  echo      and tick "Add python.exe to PATH" during setup. Then run this file again.
  goto :fail
)
echo  [1/7] Using %PY%
%PY% --version

rem ---- 2. virtual environment ----------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo  [2/7] Creating virtual environment .venv ...
  %PY% -m venv .venv || goto :fail
) else (
  echo  [2/7] Virtual environment found.
)
set "VPY=%CD%\.venv\Scripts\python.exe"

rem ---- 3. dependencies -----------------------------------------------------
echo  [3/7] Installing pinned dependencies (first time takes a few minutes) ...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements-dev.txt || goto :fail

rem ---- 4. tests ------------------------------------------------------------
echo  [4/7] Running automated tests ...
set "QT_QPA_PLATFORM=offscreen"
"%VPY%" -m pytest -q
if errorlevel 1 (
  echo  [X] Tests failed - the app was NOT built. Read the messages above.
  goto :fail
)
set "QT_QPA_PLATFORM="

rem ---- 5. PyInstaller ------------------------------------------------------
echo  [5/7] Building with PyInstaller ...
"%VPY%" -m PyInstaller NomLoyal.spec --noconfirm --clean || goto :fail
if not exist "dist\NomLoyal\NomLoyal.exe" (
  echo  [X] dist\NomLoyal\NomLoyal.exe was not created.
  goto :fail
)

rem ---- 6. extra files ------------------------------------------------------
echo  [6/7] Copying README, templates and docs ...
copy /y README.md "dist\NomLoyal\" >nul
xcopy /e /i /y templates "dist\NomLoyal\templates" >nul
xcopy /e /i /y docs "dist\NomLoyal\docs" >nul

rem ---- 7. self-test of the built app ---------------------------------------
echo  [7/7] Testing the built program ...
del /q "%TEMP%\nomloyal_selftest.txt" >nul 2>&1
start "" /wait "dist\NomLoyal\NomLoyal.exe" --selftest --report "%TEMP%\nomloyal_selftest.txt"
findstr /c:"SELFTEST OK" "%TEMP%\nomloyal_selftest.txt" >nul 2>&1
if errorlevel 1 (
  echo  [X] The built program failed its self-test:
  type "%TEMP%\nomloyal_selftest.txt" 2>nul
  goto :fail
)

echo.
echo  ==============================================
echo   DONE.  Your app:  %CD%\dist\NomLoyal\NomLoyal.exe
echo  ==============================================
echo   Copy the whole dist\NomLoyal folder to the shop PC (keep all files together).
echo   First start: a welcome screen creates the store and the Admin account.
echo.
pause
exit /b 0

:fail
echo.
echo  ---------------- BUILD FAILED ----------------
echo  Troubleshooting:
echo   - No internet / proxy: pip cannot download packages. Connect and run again.
echo   - "Access is denied": close NomLoyal.exe if it is running, then run again.
echo   - Antivirus may block PyInstaller output: allow this folder, then run again.
echo   - Python errors: delete the .venv folder and run again.
echo   - Full guide: docs\TROUBLESHOOTING.md
echo.
pause
exit /b 1
