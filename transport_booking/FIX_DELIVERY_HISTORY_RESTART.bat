@echo off
REM 🔄 Restart Odoo with module update
echo.
echo 🔄 Stopping Odoo Server...
echo.

REM Kill running Odoo processes
taskkill /F /IM odoo-bin.exe 2>nul
taskkill /F /IM python.exe 2>nul

timeout /t 3

REM Start Odoo with update flag
cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo 🚀 Starting Odoo Server with module update...
echo    Database: Npd_Transport
echo    Module: transport_booking
echo    Version: 18.0.2.5.0
echo.
echo ⏳ Wait for Odoo to start (30-60 seconds)...
echo.

python odoo-bin.py -d Npd_Transport -u transport_booking --http-port=8078

pause
