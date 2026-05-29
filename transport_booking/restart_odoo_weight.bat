@echo off
echo ========================================
echo   Restart Odoo - Weight Update
echo ========================================
echo.

cd "C:\Program Files\Odoo 18.0.20251009\server"

echo [1/2] Stopping Odoo...
taskkill /F /IM odoo-bin.exe 2>nul
timeout /t 2 /nobreak >nul

echo.
echo [2/2] Starting Odoo with update...
start "" python odoo-bin -c odoo.conf -u transport_booking -d transport_booking --http-port=8069

echo.
echo ========================================
echo   Odoo is restarting...
echo ========================================
echo.
echo Please wait about 30 seconds for Odoo to fully start
echo Then open: http://localhost:8069
echo.
pause
