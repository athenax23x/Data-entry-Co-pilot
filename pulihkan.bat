@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan jalankan.bat sekali dulu untuk menyiapkan Python.
  pause
  exit /b 1
)
set "PY=.venv\Scripts\python.exe"
echo Backup yang tersedia:
"%PY%" -m merchant_notebook.backup list
echo.
echo Tutup aplikasi dulu. Tulis nama folder backup, mis. mcn-backup-20261118-100000
echo Kalau backup dibuat dengan --recovery dan ini laptop baru, jalankan: pulihkan.bat --recovery
set "NAMA="
set /p NAMA=Nama folder backup:
if not defined NAMA exit /b 1
"%PY%" -m merchant_notebook.backup restore "merchant_data\backups\%NAMA%" %*
pause
