@echo off
echo ======================================
echo  Update Vehicle Tracking Module
echo  - Arrow Icon (Beautiful Edition)
echo  - Mileage Label Update
echo ======================================
echo.
echo Icon Features:
echo  [✓] Arrow pointing UP/NORTH by default
echo  [✓] Rotates correctly with vehicle direction
echo  [✓] Green circle = engine ON
echo  [✓] Red circle = engine OFF
echo  [✓] Shadow effect for better visibility
echo  [✓] White background circle
echo.
echo Label Changes:
echo  [✓] "ระยะทาง" → "เลขไมล์"
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
echo Upgrade Completed Successfully!
echo ======================================
echo.
echo Please test:
echo 1. Refresh browser (Ctrl + F5)
echo 2. Open vehicle tracking page
echo 3. Click "View on Map"
echo 4. Check:
echo    - Arrow points UP when course = 0
echo    - Arrow rotates with vehicle direction
echo    - Color changes (green/red)
echo    - Label shows "เลขไมล์"
echo.
pause
