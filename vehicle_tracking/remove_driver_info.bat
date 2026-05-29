@echo off
echo ======================================
echo  Remove Driver Information
echo  Update Vehicle Tracking Module
echo ======================================
echo.
echo Changes:
echo  [x] Removed: ชื่อพนักงานขับรถ (driver_name)
echo  [x] Removed: รหัสพนักงานขับรถ (driver_id)
echo  [x] Removed: เลขใบขับขี่ (license_id)
echo  [x] Removed: เลขบัตรประชาชน (personal_id)
echo  [x] Removed: ประเภทบัตร (card_type)
echo  [x] Removed: เวลาสแกนบัตร (card_swipe_time)
echo.
echo Cleaned from:
echo  - Model fields
echo  - Form View
echo  - Map Template
echo  - API Controller
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
echo Driver information has been removed from:
echo  [✓] Database model
echo  [✓] Form view (no more driver section)
echo  [✓] Map info panel
echo  [✓] API responses
echo.
echo IMPORTANT: Old driver data will remain in database
echo but will not be displayed or updated anymore.
echo.
echo Please refresh your browser (Ctrl+F5) and test!
pause
