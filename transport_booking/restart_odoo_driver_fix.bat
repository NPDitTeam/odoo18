@echo off
REM ========================================
REM 🔧 Restart Odoo - Driver Name Fix
REM ========================================

echo.
echo =========================================
echo   🔧 Restarting Odoo for Driver Name Fix
echo =========================================
echo.

REM หา PID ของ Odoo process
echo 📍 หาตำแหน่ง Odoo process...
for /f "tokens=2" %%A in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| find "PID"') do (
    set PID=%%A
)

if defined PID (
    echo 🛑 ปิด Odoo (PID: %PID%)...
    taskkill /PID %PID% /F
    timeout /T 3 /NOBREAK
) else (
    echo ⚠️  ไม่พบ Odoo process - อาจปิดอยู่แล้ว
)

echo.
echo 🚀 รีสตาร์ท Odoo...
cd /d "C:\Program Files\Odoo 18.0.20251009\server"

python odoo-bin.py -c odoo.conf --dev=reload

echo.
echo ✅ เสร็จ! Odoo กำลังรันอยู่
pause
