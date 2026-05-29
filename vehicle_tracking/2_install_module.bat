@echo off
echo ======================================
echo  Install Vehicle Tracking Module
echo ======================================
echo.

SET /P DB_NAME="Enter your database name: "

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo Installing module: vehicle_tracking
echo Database: %DB_NAME%
echo.

python odoo-bin -c odoo.conf -d %DB_NAME% -i vehicle_tracking --stop-after-init --log-level=info

echo.
echo ======================================
echo Installation Completed!
echo ======================================
echo.
echo Please run: 3_start_odoo.bat
pause
