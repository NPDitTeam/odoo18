@echo off
echo ========================================
echo RESTART ODOO - Planned End Date T Fix
echo ========================================
echo.
echo Changes made in Odoo:
echo 1. Added planned_end_date_t parameter in API
echo 2. Save planned_end_date_t when completing delivery
echo 3. Added logging for debugging
echo.
echo ========================================
cd /d "C:\Program Files\Odoo 18.0.20251009"
echo.
echo Stopping Odoo service...
net stop "Odoo 18.0-20251009"
timeout /t 3

echo.
echo Starting Odoo service...
net start "Odoo 18.0-20251009"

echo.
echo ========================================
echo Odoo restarted successfully!
echo ========================================
echo.
echo Now test in the app:
echo 1. Complete a delivery
echo 2. Check if planned_end_date_t is saved
echo.
pause
