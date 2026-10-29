@echo off
rem ===========================================================================
rem  NomLoyal - one-click Windows build.  Double-click this file.
rem  It installs Python 3.12 if needed, downloads every library, runs the tests,
rem  builds dist\NomLoyal\NomLoyal.exe and tests it.  The window never closes by
rem  itself; everything is also written to build_log.txt.
rem ===========================================================================
if /i "%CI%"=="true" goto :start
if /i not "%~1"=="__inner" (
  cmd /k ""%~f0" __inner"
  exit /b
)
:start
setlocal EnableExtensions
title NomLoyal - build Windows app
cd /d "%~dp0"
set "LOG=%CD%\build_log.txt"
echo NomLoyal build %DATE% %TIME% > "%LOG%"
echo.
echo  ==============================================
echo    NomLoyal - one-click Windows build
echo  ==============================================
echo  Folder: %CD%
echo  Your shop data in LOCALAPPDATA\Devnom\NomLoyal is never touched.
echo.

call :find_python
if defined PY goto :have_python
echo  [1/7] Python 3.12 is not installed - installing it now. This needs internet.
call :install_python
call :find_python
if defined PY goto :have_python
echo.
echo  [X] Python could not be installed automatically.
echo      Install Python 3.12 from https://www.python.org/downloads/windows/
echo      and tick "Add python.exe to PATH". Then double-click build.bat again.
goto :fail

:have_python
echo  [1/7] Python found: %PY%
"%PY%" --version
"%PY%" --version >> "%LOG%" 2>&1

if exist ".venv\Scripts\python.exe" goto :have_venv
echo  [2/7] Creating the virtual environment .venv ...
"%PY%" -m venv .venv >> "%LOG%" 2>&1
if errorlevel 1 goto :fail_venv
:have_venv
set "VPY=%CD%\.venv\Scripts\python.exe"
if not exist "%VPY%" goto :fail_venv
echo  [2/7] Virtual environment ready.

echo  [3/7] Downloading and installing all libraries - first time takes 3 to 10 minutes ...
"%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1
"%VPY%" -m pip install -r requirements-dev.txt
if errorlevel 1 goto :fail_pip
"%VPY%" -m pip freeze >> "%LOG%" 2>&1

echo  [4/7] Running the automated tests ...
set "QT_QPA_PLATFORM=offscreen"
"%VPY%" -m pytest -q
if errorlevel 1 goto :fail_tests
set "QT_QPA_PLATFORM="

echo  [5/7] Building NomLoyal.exe with PyInstaller - takes a few minutes ...
"%VPY%" -m PyInstaller NomLoyal.spec --noconfirm --clean >> "%LOG%" 2>&1
if errorlevel 1 goto :fail_build
if not exist "dist\NomLoyal\NomLoyal.exe" goto :fail_build

echo  [6/7] Copying README, templates and docs ...
copy /y README.md "dist\NomLoyal\" >nul
xcopy /e /i /y templates "dist\NomLoyal\templates" >nul
xcopy /e /i /y docs "dist\NomLoyal\docs" >nul

echo  [7/7] Testing the built program ...
del /q "%TEMP%\nomloyal_selftest.txt" >nul 2>&1
start "" /wait "dist\NomLoyal\NomLoyal.exe" --selftest --report "%TEMP%\nomloyal_selftest.txt"
findstr /c:"SELFTEST OK" "%TEMP%\nomloyal_selftest.txt" >nul 2>&1
if errorlevel 1 goto :fail_selftest

echo.
echo  ==============================================
echo   DONE.  Your program:
echo   %CD%\dist\NomLoyal\NomLoyal.exe
echo  ==============================================
echo   Copy the whole dist\NomLoyal folder to the shop PC - keep all files together.
echo   First start shows the Welcome screen to create the store and the Admin account.
echo   You can close this window now.
if /i not "%CI%"=="true" start "" explorer "%CD%\dist\NomLoyal"
exit /b 0

rem ---------------------------------------------------------------------------
:find_python
set "PY="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%ProgramFiles%\Python312\python.exe" "%ProgramFiles%\Python311\python.exe") do (
  if not defined PY if exist "%%~P" set "PY=%%~P"
)
if defined PY goto :eof
for /f "delims=" %%P in ('py -3.12 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if defined PY goto :eof
for /f "delims=" %%P in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if defined PY goto :eof
python --version 2>nul | findstr /r /c:"Python 3\.1[12]\." >nul
if errorlevel 1 goto :eof
for /f "delims=" %%P in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set "PY=%%P"
goto :eof

:install_python
set "PYEXE=%TEMP%\python-3.12.8-amd64.exe"
echo      Downloading Python 3.12.8 from python.org ...
curl -L --fail -o "%PYEXE%" https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe >> "%LOG%" 2>&1
if not exist "%PYEXE%" powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe -OutFile '%PYEXE%'" >> "%LOG%" 2>&1
if not exist "%PYEXE%" goto :eof
echo      Installing Python 3.12.8 for this user - no admin rights needed ...
"%PYEXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 >> "%LOG%" 2>&1
goto :eof

rem ---------------------------------------------------------------------------
:fail_venv
echo  [X] Could not create the virtual environment. Delete the .venv folder and try again.
goto :fail
:fail_pip
echo  [X] Downloading the libraries failed. Check the internet connection, then run build.bat again.
goto :fail
:fail_tests
echo  [X] Tests failed - the program was NOT built. Send build_log.txt and this window's text to support.
goto :fail
:fail_build
echo  [X] PyInstaller could not build NomLoyal.exe. Details are in build_log.txt.
echo      If antivirus removed the file, allow this folder and run again.
goto :fail
:fail_selftest
echo  [X] The built program failed its self-test:
type "%TEMP%\nomloyal_selftest.txt" 2>nul
goto :fail
:fail
echo.
echo  ------------------- BUILD FAILED -------------------
echo   Log file: %LOG%
echo   - No internet or proxy: connect and run build.bat again.
echo   - Access is denied: close NomLoyal.exe, then run again.
echo   - Strange Python errors: delete the .venv folder and run again.
echo   - More help: docs\TROUBLESHOOTING.md
echo  ----------------------------------------------------
exit /b 1
