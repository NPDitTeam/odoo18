@echo off
echo ========================================
echo  Restarting Odoo for Tracking Update
echo ========================================
echo.

REM Stop Odoo Service
echo [1/2] Stopping Odoo service...
net stop odoo18
timeout /t 3 /nobreak >nul

REM Start Odoo Service
echo [2/2] Starting Odoo service...
net start odoo18
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo  Odoo Restarted Successfully!
echo ========================================
echo.
echo Changes applied:
echo - Added tracking record creation on job start
echo - Updated vehicle_booking.py
echo - Updated vehicle_booking_views.xml
echo.
echo Next steps:
echo 1. Login to Odoo18
echo 2. Start a job from mobile app
echo 3. Check "Tracking" tab in booking form
echo.
pause
