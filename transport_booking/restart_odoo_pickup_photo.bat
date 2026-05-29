@echo off
echo ========================================
echo  Restarting Odoo - Pickup Photo Update
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
echo - Pickup photo now displays at top of tracking tab
echo - Actual pickup time shown below photo
echo - Delivery photos grouped separately at bottom
echo - Better layout and organization
echo.
echo Next steps:
echo 1. Login to Odoo18: http://localhost:8078
echo 2. Start a job from mobile app (with photo)
echo 3. Check booking form - Tracking tab
echo 4. You should see pickup photo at the top!
echo.
pause
