@echo off
chcp 65001 >nul
REM ════════════════════════════════════════════════════════════
REM 🔄 RESTART ODOO - Auto-Refresh Badge Fix
REM ════════════════════════════════════════════════════════════

echo.
echo ⏹️  Stopping Odoo Server...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Odoo*" 2>nul
timeout /t 2 /nobreak

echo.
echo 🧹 Clearing Python Cache...
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    echo   Removing: %%d
    rmdir /s /q "%%d" 2>nul
)

echo.
echo 🧹 Clearing Odoo Cache...
if exist "C:\ProgramData\Odoo\filestore" (
    echo   Cache folder exists
)

echo.
echo 🚀 Starting Odoo Server...
cd /d "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin.py -c odoo.conf --dev=all 2>&1 | find /v "INFO:werkzeug"

echo.
pause
