@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan jalankan.bat sekali dulu untuk menyiapkan Python.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Pemakaian: impor-portabel.bat NAMA_FILE.mcnx
  echo Contoh:    impor-portabel.bat D:\merchants.mcnx  (tutup aplikasi dulu)
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m merchant_notebook.portable import --file "%~1"
set "RC=%errorlevel%"
pause
exit /b %RC%
