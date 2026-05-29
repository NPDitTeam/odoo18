@echo off
echo ========================================
echo  QUICK FIX: Auto-Refresh Module
echo ========================================
echo.
echo This script will:
echo 1. Restart Odoo service
echo 2. Wait for Odoo to be ready
echo.
echo After this, you need to:
echo 1. Login to Odoo
echo 2. Go to Settings ^> Apps
echo 3. Remove "Apps" filter
echo 4. Search "transport_booking"
echo 5. Click Upgrade button
echo 6. Logout and clear browser cache
echo 7. Login again and test
echo.
pause

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo ========================================
echo  Step 1: Stopping Odoo...
echo ========================================
net stop odoo-server-18.0
if %errorlevel% neq 0 (
    echo Failed to stop Odoo service!
    echo Please run this script as Administrator
    pause
    exit /b 1
)

echo.
echo Waiting 5 seconds...
timeout /t 5

echo.
echo ========================================
echo  Step 2: Starting Odoo...
echo ========================================
net start odoo-server-18.0
if %errorlevel% neq 0 (
    echo Failed to start Odoo service!
    pause
    exit /b 1
)

echo.
echo Waiting for Odoo to be ready (30 seconds)...
timeout /t 30

echo.
echo ========================================
echo  SUCCESS!
echo ========================================
echo.
echo Odoo has been restarted successfully!
echo.
echo IMPORTANT - Next steps:
echo ========================================
echo.
echo 1. Open Odoo in your browser: http://localhost:8069
echo.
echo 2. Login with your credentials
echo.
echo 3. Go to: Settings ^> Apps
echo.
echo 4. Remove the "Apps" filter (click X next to Apps)
echo.
echo 5. In search box, type: transport_booking
echo.
echo 6. Click the ⋮ (3 dots) button
echo.
echo 7. Click "Upgrade"
echo.
echo 8. Wait for upgrade to complete
echo.
echo 9. Logout from Odoo
echo.
echo 10. Clear browser cache:
echo     - Press Ctrl+Shift+Delete
echo     - Select "All time"
echo     - Check: Cached images and files
echo     - Click Clear data
echo.
echo 11. Close ALL browser windows
echo.
echo 12. Open browser again and login
echo.
echo 13. Test: Open Vehicle Booking ^> Click "ตำแหน่ง GPS" button
echo.
echo 14. Press F12 to open Console
echo.
echo 15. You should see: "Auto-refresh เปิดใช้งาน (ทุก 30 นาที)"
echo.
echo ========================================
echo.
echo If you still don't see the notification,
echo read: TROUBLESHOOTING_AUTO_REFRESH.md
echo.
echo ========================================
pause
