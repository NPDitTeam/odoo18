@echo off
echo ========================================
echo  Restart Odoo - All Updates
echo ========================================
echo.
echo This will restart Odoo to apply:
echo  - GPS tracking API updates
echo  - Delivery view improvements
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
echo Updates applied:
echo  1. GPS tracking API enhanced
echo  2. Delivery view improved (larger images, better layout)
echo.
echo Next step:
echo  Rebuild Flutter app using:
echo    rebuild_all_fixes.bat
echo.
pause
