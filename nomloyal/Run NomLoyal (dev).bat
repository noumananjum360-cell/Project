@echo off
rem Run NomLoyal from source (development mode). Run build.bat once first to create .venv.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" ( start "" ".venv\Scripts\pythonw.exe" main.py ) else ( python main.py )
