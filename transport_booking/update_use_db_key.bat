@echo off
echo ========================================
echo Update Module - Use Database API Key
echo ========================================

echo.
echo Stopping Odoo...
net stop "odoo-server-18.0"

timeout /t 3 /nobreak

echo.
echo Starting Odoo...
net start "odoo-server-18.0"

timeout /t 10 /nobreak

echo.
echo Updating module...
cd "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin -u transport_booking -d Npd_Transport --stop-after-init

echo.
echo Final restart...
net stop "odoo-server-18.0"
timeout /t 2 /nobreak
net start "odoo-server-18.0"

echo.
echo ========================================
echo Done! 
echo ========================================
echo.
echo Now using API key from database:
echo   google_maps_api_key = AIzaSyBQJDTjXLNYEgErUc1gybeHfBDsIkN7Mi0
echo.
echo Please:
echo   1. Close ALL browser windows
echo   2. Open Incognito/Private window
echo   3. Test tracking map
echo ========================================
pause
