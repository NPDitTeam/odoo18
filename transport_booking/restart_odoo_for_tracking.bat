@echo off
echo ========================================
echo  Restarting Odoo for GPS Tracking Fix
echo ========================================
echo.
echo This will restart Odoo service to apply the tracking updates.
echo.
pause

echo.
echo Stopping Odoo service...
net stop Odoo18

timeout /t 3 /nobreak > nul

echo.
echo Starting Odoo service...
net start Odoo18

echo.
echo ========================================
echo  Odoo restarted successfully!
echo ========================================
echo.
echo GPS Tracking updates are now active.
echo.
echo Next steps:
echo 1. Rebuild Flutter app: flutter clean ^&^& flutter pub get ^&^& flutter run
echo 2. Test GPS tracking when starting a job
echo.
pause
