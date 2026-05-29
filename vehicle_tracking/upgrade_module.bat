@echo off
echo ======================================
echo  Upgrade Vehicle Tracking Module
echo ======================================
echo.

SET /P DB_NAME="Enter your database name: "

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo Upgrading module: vehicle_tracking
echo Database: %DB_NAME%
echo.

python odoo-bin -c odoo.conf -d %DB_NAME% -u vehicle_tracking --stop-after-init --log-level=info

echo.
echo ======================================
echo Upgrade Completed!
echo ======================================
echo.
echo Please restart Odoo and refresh your browser
pause
