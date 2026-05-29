@echo off
chcp 65001 >nul
cls
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║   🔧 แก้ไขปัญหา Auto-refresh ทั้งหมด (แก้ครบทุกปัญหา!)      ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo 📋 ปัญหาที่จะแก้ไข:
echo    1. ✅ แสดง "ทุก 5 นาที" แม้ตั้งค่า 30 นาที
echo    2. ✅ ไม่หยุด auto-refresh เมื่อ state = 'done'
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

echo 🚀 STEP 1: แก้ไขปัญหา tracking_interval และ hardcode text...
echo.
python FIX_AUTO_REFRESH_FINAL.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ STEP 1 ล้มเหลว!
    pause
    exit /b 1
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

echo 🚀 STEP 2: แก้ไขปัญหาการไม่หยุด auto-refresh เมื่อ done...
echo.
python FIX_STOP_AUTO_REFRESH.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ STEP 2 ล้มเหลว!
    pause
    exit /b 1
)

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo ✅ แก้ไขเสร็จสมบูรณ์ทั้ง 2 ปัญหา!
echo.
echo 📋 สิ่งที่แก้ไขแล้ว:
echo    ✅ แก้ไข hardcode "ทุก 5 นาที" ให้อ่านจาก CONFIG
echo    ✅ เพิ่มการ force reload settings จาก API
echo    ✅ เพิ่มการเช็ค state ตอนโหลดครั้งแรก
echo    ✅ เพิ่ม function checkBookingState()
echo    ✅ ปรับปรุงการหยุด timer เมื่อ state = 'done'
echo    ✅ ป้องกันการเริ่ม timer ใหม่หลังงานเสร็จ
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

echo 🔄 กำลัง restart Odoo...
echo.
call restart_odoo_final.bat

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo ✅ เสร็จสิ้นการแก้ไขทั้งหมด!
echo.
echo 📋 ขั้นตอนต่อไป:
echo    1. เคลียร์ cache เบราว์เซอร์ (Ctrl+Shift+Delete)
echo    2. Reload หน้า tracking map
echo    3. เปิด Console (F12) เพื่อดู log
echo    4. ตรวจสอบว่า:
echo       - แสดง "ทุก 30 นาที" (หรือค่าที่ตั้งไว้)
echo       - หยุด auto-refresh เมื่อ state = 'done'
echo       - แสดง "✅ การขนส่งเสร็จสิ้นแล้ว"
echo.
echo 📄 อ่านรายละเอียดเพิ่มเติมที่:
echo    - FIX_STOP_AUTO_REFRESH_DOCS.md
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

pause
