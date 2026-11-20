@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan jalankan.bat sekali dulu untuk menyiapkan Python.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Pemakaian: ekspor-portabel.bat NAMA_FILE.mcnx
  echo Contoh:    ekspor-portabel.bat D:\merchants.mcnx
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m merchant_notebook.portable export --file "%~1"
set "RC=%errorlevel%"
pause
exit /b %RC%
