@echo off
REM Run NomLoad Counter from source (no installer needed). Double-click this file.
setlocal EnableExtensions
title NomLoad Counter
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && (py -3.11 -c "import sys" >nul 2>nul && set "PY=py -3.11")
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Python was not found. Install Python 3.11 64-bit from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo First start: installing NomLoad (a few minutes^)...
  %PY% -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 goto :fail
exit /b 0
:fail
echo.
echo NomLoad could not start - read the messages above.
echo The log file is in %%PROGRAMDATA%%\Devnom\NomLoad\logs\nomload.log
pause
exit /b 1
