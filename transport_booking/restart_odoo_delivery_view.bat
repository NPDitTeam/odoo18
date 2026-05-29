@echo off
echo ========================================
echo  Restart Odoo - Delivery Info Update
echo ========================================
echo.
echo This will restart Odoo to apply the delivery information view updates.
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
echo The delivery information view has been updated.
echo.
echo Changes:
echo  - Show delivery info immediately when available
echo  - Better organized layout
echo  - Larger images for easier viewing
echo  - Clear section labels
echo.
pause
