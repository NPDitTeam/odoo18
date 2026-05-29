@echo off
echo ======================================
echo  GPS Tracking Integration
echo  Link Vehicle Booking with GPS
echo ======================================
echo.
echo New Features:
echo  [+] Auto-link vehicles by license plate
echo  [+] Real-time GPS data in booking form
echo  [+] GPS tracking map button
echo  [+] Vehicle speed display
echo  [+] GPS status indicator
echo.

SET /P DB_NAME="Enter your database name: "

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo Stopping Odoo Service...
net stop "odoo-server-18.0"

echo.
echo Upgrading modules:
echo  - transport_booking (with GPS link)
echo  - vehicle_tracking
echo Database: %DB_NAME%
echo.

python odoo-bin -c odoo.conf -d %DB_NAME% -u transport_booking,vehicle_tracking --stop-after-init --log-level=info

echo.
echo Starting Odoo Service...
net start "odoo-server-18.0"

echo.
echo ======================================
echo GPS Integration Completed!
echo ======================================
echo.
echo What's new:
echo  1. Auto GPS vehicle detection by license plate
echo  2. Smart button showing real-time speed
echo  3. GPS status and last update time
echo  4. Direct link to GPS tracking map
echo  5. Full GPS data access button
echo.
echo How to use:
echo  1. Create/Open a booking
echo  2. Select transport order (with license plate)
echo  3. System will auto-find GPS vehicle
echo  4. Click GPS button to see real-time tracking
echo.
echo Please refresh your browser (Ctrl+F5) and test!
pause
