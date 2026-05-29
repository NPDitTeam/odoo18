@echo off
chcp 65001 >nul
echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║      🛑 แก้ไขให้หยุด Auto-refresh เมื่อ state = done     ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.

echo 🚀 กำลังรันสคริปต์แก้ไข...
echo.

python FIX_STOP_AUTO_REFRESH.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ สคริปต์รันสำเร็จ!
    echo.
    echo 🔄 กำลัง restart Odoo...
    echo.
    call restart_odoo_final.bat
) else (
    echo.
    echo ❌ เกิดข้อผิดพลาด!
    echo กรุณาตรวจสอบ error message ด้านบน
    echo.
    pause
)
