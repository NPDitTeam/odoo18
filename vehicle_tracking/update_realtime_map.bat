@echo off
echo ======================================
echo  Upgrade Vehicle Tracking Module
echo  with Real-time Map Feature
echo ======================================
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
echo Changes:
echo - Fixed debug mode issue
echo - Added Real-time map with auto-refresh every 1 minute
echo - Cron job updated to fetch GPS data every 1 minute
echo.
echo Please refresh your browser and test!
pause
