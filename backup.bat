@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan jalankan.bat sekali dulu untuk menyiapkan Python.
  if /i not "%~1"=="--quiet" pause
  exit /b 1
)
".venv\Scripts\python.exe" -m merchant_notebook.backup create %*
set "RC=%errorlevel%"
if /i not "%~1"=="--quiet" pause
exit /b %RC%
