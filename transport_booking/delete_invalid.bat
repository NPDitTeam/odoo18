@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo =========================================================
echo Deleting Invalid Records
echo =========================================================
echo.

set PGPASSWORD=odoo

echo Step 1: Deleting invalid records...
echo.

psql -h localhost -U odoo -d Npd_Transport -c "DELETE FROM vehicle_tracking WHERE driver_id NOT IN (SELECT id FROM vehicle_driver WHERE id IS NOT NULL) AND driver_id IS NOT NULL;"

if errorlevel 1 (
    echo.
    echo Error: psql not found
    echo Please install PostgreSQL client tools
    echo Or use pgAdmin GUI
    pause
    exit /b 1
)

echo.
echo Step 2: Checking results...
echo.

psql -h localhost -U odoo -d Npd_Transport -c "SELECT COUNT(*) as total_records FROM vehicle_tracking;"

echo.
echo =========================================================
echo Done! Ready to restart Odoo
echo =========================================================
echo.

pause
