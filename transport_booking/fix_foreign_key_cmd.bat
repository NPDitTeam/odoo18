@echo off
REM =======================================================
REM 🔧 Fix Foreign Key Violation via psql (CMD)
REM =======================================================

setlocal enabledelayedexpansion

echo.
echo =========================================================
echo   🔧 Fixing Foreign Key Violation via Command Line
echo =========================================================
echo.

REM ตั้งค่า Database
set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=Npd_Transport
set DB_USER=odoo
set DB_PASSWORD=odoo

REM ขั้นตอนที่ 1: ตรวจหา invalid records
echo [1/3] 📍 ตรวจหา invalid records...
echo.

psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "SELECT COUNT(*) as invalid_count FROM vehicle_tracking vt WHERE NOT EXISTS ( SELECT 1 FROM vehicle_driver vd WHERE vd.id = vt.driver_id ) AND vt.driver_id IS NOT NULL;"

if errorlevel 1 (
    echo ❌ ข้อผิดพลาด: ไม่สามารถเชื่อมต่อ Database
    echo ตรวจสอบ:
    echo   - PostgreSQL service กำลังรันอยู่หรือไม่?
    echo   - Database name ถูกต้องหรือไม่? (ปัจจุบัน: %DB_NAME%)
    echo   - Username ถูกต้องหรือไม่? (ปัจจุบัน: %DB_USER%)
    echo   - Password ถูกต้องหรือไม่?
    pause
    exit /b 1
)

echo.
echo ✅ เสร็จแล้ว
echo.

REM ขั้นตอนที่ 2: ถามว่าต้องการลบหรือไม่
echo [2/3] ⚠️  เตือน: จะลบ invalid records
echo.
set /p confirm="ต้องการลบ invalid records หรือไม่? (y/n): "

if /i not "%confirm%"=="y" (
    echo ยกเลิกการลบ
    pause
    exit /b 0
)

echo.
echo 🗑️  ลบ invalid records...
echo.

psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "DELETE FROM vehicle_tracking WHERE driver_id IS NOT NULL AND driver_id NOT IN ( SELECT id FROM vehicle_driver );"

if errorlevel 1 (
    echo ❌ ข้อผิดพลาด: ไม่สามารถลบ records
    pause
    exit /b 1
)

echo ✅ ลบเสร็จแล้ว
echo.

REM ขั้นตอนที่ 3: ตรวจสอบ
echo [3/3] ✅ ตรวจสอบผลลัพธ์...
echo.

psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "SELECT COUNT(*) as remaining_invalid FROM vehicle_tracking vt WHERE NOT EXISTS ( SELECT 1 FROM vehicle_driver vd WHERE vd.id = vt.driver_id ) AND vt.driver_id IS NOT NULL;"

echo.
echo =========================================================
echo   ✅ เสร็จแล้ว!
echo =========================================================
echo.
echo 📌 ต่อไป:
echo    1. รีสตาร์ท Odoo
echo    2. ทดสอบ API
echo.

pause
