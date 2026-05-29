@echo off
REM ลบข้อมูล invalid records ด้วยวิธีเรียบง่าย

setlocal enabledelayedexpansion

set PGPASSWORD=odoo

echo.
echo Deleting invalid records...
echo.

REM Delete invalid records
psql -h localhost -U odoo -d Npd_Transport -c "DELETE FROM vehicle_tracking WHERE driver_id IS NOT NULL AND driver_id NOT IN (SELECT id FROM vehicle_driver);" 2>nul

if errorlevel 1 (
    echo psql not found - using direct database cleanup...
    echo.
    echo Please open pgAdmin and run this SQL:
    echo.
    echo DELETE FROM vehicle_tracking WHERE driver_id IS NOT NULL AND driver_id NOT IN (SELECT id FROM vehicle_driver);
    echo.
    pause
    exit /b 1
)

echo Done!
echo.

REM Check result
psql -h localhost -U odoo -d Npd_Transport -c "SELECT COUNT(*) as records_remaining FROM vehicle_tracking;" 2>nul

echo.
pause
