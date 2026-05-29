@echo off
echo ================================
echo  FIX COUNTDOWN TIMER
echo ================================
echo.
echo This will fix the countdown timer to use minutes instead of seconds
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
echo Please refresh the tracking map page in your browser
echo The countdown timer should now show correct minutes
echo.
pause
