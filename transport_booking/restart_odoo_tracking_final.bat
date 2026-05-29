@echo off
echo ========================================
echo Restarting Odoo for Tracking Fix
echo ========================================

echo.
echo Stopping Odoo service...
net stop "odoo-server-18.0"

echo.
echo Waiting 3 seconds...
timeout /t 3 /nobreak

echo.
echo Starting Odoo service...
net start "odoo-server-18.0"

echo.
echo ========================================
echo Done! 
echo Please refresh your browser with Ctrl+F5
echo ========================================
pause
