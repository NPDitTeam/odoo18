@echo off
REM =======================================================
REM 🔧 Force Delete Invalid Records - Direct SQL
REM =======================================================

setlocal enabledelayedexpansion

echo.
echo =========================================================
echo   🔧 Deleting Invalid Records Directly
echo =========================================================
echo.

REM ตั้งค่า Database
set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=Npd_Transport
set DB_USER=odoo
set DB_PASSWORD=odoo

echo ⚠️  ขั้นตอน 1: ลบ Foreign Key Constraint เก่า
echo.

psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "ALTER TABLE vehicle_tracking DROP CONSTRAINT IF EXISTS vehicle_tracking_driver_id_fkey CASCADE;"

echo ✅ ลบ Constraint เสร็จแล้ว
echo.
echo ⚠️  ขั้นตอน 2: ลบข้อมูล invalid ทั้งหมด
echo.

psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "DELETE FROM vehicle_tracking WHERE driver_id NOT IN (SELECT id FROM vehicle_driver WHERE id IS NOT NULL) AND driver_id IS NOT NULL;"

echo ✅ ลบข้อมูล invalid เสร็จแล้ว
echo.
echo ✅ ขั้นตอน 3: ตรวจสอบผลลัพธ์
echo.

psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "SELECT COUNT(*) as total_records FROM vehicle_tracking;"

echo.
echo =========================================================
echo   ✅ เสร็จแล้ว! พร้อม Restart Odoo
echo =========================================================
echo.

pause
