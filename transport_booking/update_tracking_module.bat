@echo off
echo ========================================
echo Updating Odoo Module - Tracking Fix
echo ========================================

echo.
echo Step 1: Stopping Odoo...
net stop "odoo-server-18.0"

timeout /t 3 /nobreak

echo.
echo Step 2: Starting Odoo...
net start "odoo-server-18.0"

timeout /t 5 /nobreak

echo.
echo Step 3: Updating transport_booking module...
cd "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin -u transport_booking -d Npd_Transport --stop-after-init

echo.
echo Step 4: Restarting Odoo again...
net stop "odoo-server-18.0"
timeout /t 2 /nobreak
net start "odoo-server-18.0"

echo.
echo ========================================
echo Done! Now do these steps:
echo 1. Close ALL browser windows
echo 2. Open browser in Incognito/Private mode
echo 3. Go to: http://127.0.0.1:8069
echo 4. Login and check the tracking map
echo ========================================
pause
