@echo off
echo ======================================
echo  FIX: Google Maps API Error
echo  Switch to Leaflet (OpenStreetMap)
echo ======================================
echo.
echo Changes:
echo - Removed Google Maps API dependency
echo - Using Leaflet + OpenStreetMap (FREE)
echo - No API Key required
echo - Better performance
echo.

SET /P DB_NAME="Enter your database name: "

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo Stopping Odoo Service...
net stop "odoo-server-18.0"

echo.
echo Upgrading module: vehicle_tracking
echo Database: %DB_NAME%
echo.

python odoo-bin -c odoo.conf -d %DB_NAME% -u vehicle_tracking --stop-after-init --log-level=info

echo.
echo Starting Odoo Service...
net start "odoo-server-18.0"

echo.
echo ======================================
echo Upgrade Completed!
echo ======================================
echo.
echo The map now uses OpenStreetMap (Free!)
echo - No API Key needed
echo - Auto-refresh every 1 minute
echo - Works perfectly without billing
echo.
echo Please refresh your browser (Ctrl+F5) and test!
pause
