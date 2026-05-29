@echo off
chcp 65001 >nul
cls
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║   🔧 แก้ไข Logic Cannot get user ID (v4.2 - FINAL FIX!)      ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo 📋 การแก้ไข:
echo    ✅ Import session module โดยตรง
echo    ✅ ลอง 5 วิธีในการหา user ID
echo    ✅ เพิ่ม debug log ละเอียดกว่าเดิม
echo    ✅ แก้ไข logic การเช็ค session
echo    ✅ Auto-refresh ยังทำงานแม้หา user ID ไม่ได้ (ใช้ default 30 นาที)
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
echo       - เลือก "Cached images and files"
echo       - เลือก "All time"
echo       - คลิก "Clear data"
echo.
echo    2. ปิดแท็บทั้งหมด แล้วเปิดใหม่
echo.
echo    3. กลับไปที่หน้า List View
echo.
echo    4. เปิด Console (F12) ตรวจสอบว่า:
echo       ✅ ไม่มี error "Cannot get user ID"
echo       ✅ เห็น "✅ Got user ID from session module: X"
echo          หรือ "✅ Got user ID from this.env.session.uid: X"
echo       ✅ เห็น "✨ SUCCESS! Loaded tracking_interval: 30 minutes ✨"
echo       ✅ แสดง notification "ทุก 30 นาที"
echo.
echo 💡 ถ้ายังมี error:
echo    - ดู Console log ทั้งหมดแล้วส่งภาพให้ดู
echo    - ตรวจสอบว่า cache ถูกเคลียร์จริง
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

pause
