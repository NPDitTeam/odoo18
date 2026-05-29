@echo off
chcp 65001 >nul
cls
echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║   🔧 แก้ไข "Service user is not available" error             ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.
echo 📋 การแก้ไข:
echo    ✅ ลบ useService("user") ที่ไม่มีใน Odoo 18
echo    ✅ ใช้ this.env.session.uid แทน
echo    ✅ เพิ่ม fallback methods หลายแบบ
echo    ✅ Default tracking_interval = 30 นาที
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
echo       ✅ ไม่มี error "Service user is not available"
echo       ✅ แสดง "👤 Got user ID from session.uid: X"
echo       ✅ แสดง "🔄 Auto-refresh เปิดใช้งาน (ทุก 30 นาที)"
echo       ✅ ไม่มี OwlError
echo.
echo 💡 Console log ที่ดีควรมี:
echo    🚀 [Auto-Refresh v4.1] Module loaded!
echo    🔧 [Auto-Refresh] Setup called for model: vehicle.tracking
echo    ✅ [Auto-Refresh] This is vehicle.tracking view!
echo    👤 [Auto-Refresh] Got user ID from session.uid: 2
echo    ✨ Loaded FRESH tracking_interval: 30 minutes ✨
echo    🔄 [Auto-Refresh] Starting auto-refresh
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

pause
