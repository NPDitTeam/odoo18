@echo off
echo ========================================
echo RESTART ODOO - DateTime Conversion Fix
echo ========================================
echo.
echo Fix: Convert planned_end_date_t string to datetime object
echo Before: "2025-11-21 21:58:48" (string)
echo After: datetime(2025, 11, 21, 21, 58, 48) (datetime object)
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
echo Now test completing a delivery again.
echo Check the log for:
echo    type: datetime (not str!)
echo.
pause
