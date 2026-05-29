@echo off
echo ======================================
echo  Update Module List and Install
echo ======================================
echo.

SET /P DB_NAME="Enter your database name: "

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo Step 1: Update module list...
python odoo-bin -c odoo.conf -d %DB_NAME% -u base --stop-after-init --log-level=warn

echo.
echo Step 2: Install vehicle_tracking...
python odoo-bin -c odoo.conf -d %DB_NAME% -i vehicle_tracking --stop-after-init --log-level=info

echo.
echo ======================================
echo Installation Completed!
echo ======================================
pause
