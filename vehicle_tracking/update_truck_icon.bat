@echo off
echo ======================================
echo  Update Vehicle Tracking Module
echo  - Change marker to TRUCK ICON
echo  - Change label to MILEAGE
echo ======================================
echo.
echo Changes:
echo [1] Marker Icon Changed:
echo     - Old: Simple arrow
echo     - New: Truck icon with wheels
echo     - Color: Green (engine on) / Red (engine off)
echo     - Direction: Rotates based on vehicle course
echo.
echo [2] Field Label Changed:
echo     - Old: "ระยะทาง" (Distance)
echo     - New: "เลขไมล์" (Mileage)
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
echo What to test:
echo 1. Open vehicle tracking page
echo 2. Click "View on Map" button
echo 3. You should see:
echo    - Truck icon on map (not arrow)
echo    - Field shows "เลขไมล์" (not "ระยะทาง")
echo    - Icon rotates with vehicle direction
echo    - Icon color changes (green/red)
echo.
echo Please refresh your browser (Ctrl+F5) and test!
pause
