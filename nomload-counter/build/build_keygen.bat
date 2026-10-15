@echo off
REM Builds the vendor licence key generator (dist\NomLoadKeygen.exe). Never give this to customers.
cd /d "%~dp0\.."
call .venv-build\Scripts\activate.bat
pyinstaller --noconfirm --workpath build\work-keygen --distpath dist build\keygen.spec
