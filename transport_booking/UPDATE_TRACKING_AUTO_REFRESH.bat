@echo off
echo ================================
echo  UPDATE TRACKING AUTO-REFRESH
echo ================================
echo.
echo This will update the module to add auto-refresh feature
echo for GPS Tracking list view
echo.
pause

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

REM Stop Odoo service
echo Stopping Odoo service...
net stop odoo-server-18.0

REM Wait a moment
timeout /t 3

REM Start Odoo service
echo Starting Odoo service...
net start odoo-server-18.0

echo.
echo ================================
echo  DONE!
echo ================================
echo.
echo Module updated successfully!
echo.
echo Next steps:
echo 1. Open Odoo in your browser
echo 2. Go to Settings ^> Apps
echo 3. Search for "transport_booking"
echo 4. Click "Upgrade" button
echo 5. Test by opening GPS Tracking list
echo.
echo You should see a notification:
echo "Auto-refresh enabled (every 15 minutes)"
echo.
pause
