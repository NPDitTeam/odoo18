@echo off
echo ========================================
echo Restarting Odoo with Tracking Map Fix
echo ========================================

echo.
echo Step 1: Stopping Odoo service...
net stop "odoo-server-18.0"

timeout /t 3

echo.
echo Step 2: Starting Odoo service...
net start "odoo-server-18.0"

timeout /t 5

echo.
echo Step 3: Updating transport_booking module...
cd "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin -u transport_booking -d Npd_Transport --stop-after-init

echo.
echo ========================================
echo Done! Please refresh your browser
echo ========================================
pause
