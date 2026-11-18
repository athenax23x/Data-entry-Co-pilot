@echo off
setlocal
cd /d "%~dp0"
title Merchant Notebook

set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
  echo Python 3 belum terpasang. Pasang dari python.org ^(versi 3.10 atau lebih baru^), lalu jalankan lagi.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Menyiapkan lingkungan Python, hanya sekali. Perlu internet...
  %PYEXE% -m venv .venv
  if errorlevel 1 goto :gagal
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :gagal
)
set "PY=.venv\Scripts\python.exe"

if exist "merchant_data\merchants.db" (
  echo Membuat backup otomatis...
  "%PY%" -m merchant_notebook.backup create --keep 14 --quiet
  if errorlevel 1 echo Peringatan: backup otomatis gagal. Aplikasi tetap dijalankan.
)

"%PY%" -m merchant_notebook.api
if errorlevel 1 goto :gagal
exit /b 0

:gagal
echo.
echo Gagal. Baca pesan di atas.
pause
exit /b 1
