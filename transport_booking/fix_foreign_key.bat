@echo off
REM =======================================================
REM 🔧 Fix Foreign Key Violation - Step by Step
REM =======================================================

echo.
echo =========================================================
echo   🔧 Fixing Foreign Key Violation in vehicle_tracking
echo =========================================================
echo.
echo ⚠️  ต้องปิด Odoo ก่อน!
echo.

REM ขั้นตอนที่ 1: หยุด Odoo
echo [1/4] 🛑 ปิด Odoo process...
for /f "tokens=2" %%A in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| find "PID"') do (
    taskkill /PID %%A /F >nul 2>&1
)
timeout /T 2 /NOBREAK

echo.
echo [2/4] 📋 ขั้นตอนที่ต้องทำ:
echo.
echo    ก. เปิด pgAdmin หรือ psql
echo    ข. เชื่อมต่อ Database "Npd_Transport"
echo    ค. รัน SQL queries จาก file นี้: fix_foreign_key.sql
echo       (ดูตัวอย่าง queries ในไฟล์)
echo.
echo    หรือใช้ Command line:
echo    psql -U odoo -d Npd_Transport -f fix_foreign_key.sql
echo.

echo [3/4] ✅ หลังจากรัน SQL เสร็จแล้ว...

REM ขั้นตอนที่ 3: รีสตาร์ท Odoo
pause
echo.
echo 🚀 รีสตาร์ท Odoo...
cd /d "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin.py -c odoo.conf --dev=reload

echo.
echo ✅ เสร็จ! Odoo กำลังรันอยู่
pause
