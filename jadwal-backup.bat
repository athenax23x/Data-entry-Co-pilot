@echo off
setlocal
cd /d "%~dp0"
rem Membuat tugas Windows: backup otomatis setiap hari jam 12:30 untuk akun ini. Hapus dengan: schtasks /Delete /TN MerchantNotebookBackup /F
schtasks /Create /SC DAILY /ST 12:30 /TN "MerchantNotebookBackup" /TR "\"%~dp0backup.bat\" --quiet" /F
pause
