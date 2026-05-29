@echo off
chcp 65001 >nul
cls
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║   🔧 แก้ไข tracking_auto_refresh.js (userId undefined error)  ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo 📋 ปัญหาที่แก้ไข:
echo    ✅ แก้ error "Cannot read properties of undefined (reading 'userId')"
echo    ✅ เปลี่ยน default tracking_interval จาก 5 → 30 นาที
echo    ✅ เพิ่ม error handling สำหรับการอ่าน user ID
echo    ✅ แสดงค่า tracking_interval ที่ถูกต้อง
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

echo 🔄 กำลัง restart Odoo...
echo.

cd "C:\Program Files\Odoo 18.0.20251009\server"

REM ✅ หยุด Odoo
echo 🛑 หยุด Odoo service...
net stop odoo-server-18.0

REM รอให้ service หยุดจริงๆ
timeout /t 3 /nobreak >nul

REM ✅ เริ่ม Odoo
echo 🚀 เริ่ม Odoo service...
net start odoo-server-18.0

REM รอให้ service เริ่มต้นเสร็จ
echo.
echo ⏳ รอให้ Odoo เริ่มต้นเสร็จ...
timeout /t 10 /nobreak

echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo ✅ Odoo restart เสร็จสิ้น!
echo.
echo 📋 ขั้นตอนต่อไป:
echo    1. เคลียร์ cache เบราว์เซอร์ (Ctrl+Shift+Delete)
echo    2. Hard refresh หน้า List View (Ctrl+F5)
echo    3. เปิด Console (F12) ตรวจสอบว่า:
echo       ✅ ไม่มี error "Cannot read properties of undefined"
echo       ✅ แสดง "Auto-refresh เปิดใช้งาน (ทุก 30 นาที)"
echo       ✅ Log แสดง "Got user ID from this.user.userId: X"
echo.
echo 💡 ถ้ายังมี error:
echo    - ดู Console log เพื่อตรวจสอบว่า userId มีค่าหรือไม่
echo    - ตรวจสอบว่า tracking_settings มีข้อมูลใน database
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

pause
