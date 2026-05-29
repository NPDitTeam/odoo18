@echo off
echo ========================================
echo  Restarting Odoo - Copy Link Fix
echo  แก้ไขปัญหาคัดลอก Link ไม่ได้
echo ========================================
echo.

REM Stop Odoo service
echo [1/4] Stopping Odoo service...
net stop odoo-server-18.0
timeout /t 3 /nobreak >nul

REM Start Odoo service
echo.
echo [2/4] Starting Odoo service...
net start odoo-server-18.0
timeout /t 5 /nobreak >nul

REM Open browser
echo.
echo [3/4] Opening Odoo in browser...
start http://localhost:8069

echo.
echo [4/4] รอ Odoo โหลดเสร็จ...
timeout /t 10 /nobreak >nul

echo.
echo ========================================
echo  สำเร็จ! Odoo กำลังทำงานแล้ว
echo ========================================
echo.
echo  ⚠️ สำคัญมาก!
echo  ================================
echo  ต้อง Clear Browser Cache ก่อน!
echo  ================================
echo.
echo  วิธี Clear Cache:
echo  1. Chrome/Edge: Ctrl + Shift + Delete
echo     → เลือก "Cached images and files"
echo     → Clear data
echo.
echo  2. Firefox: Ctrl + Shift + Delete
echo     → เลือก "Cache"
echo     → Clear Now
echo.
echo  หรือใช้ Hard Refresh:
echo  → Ctrl + F5
echo  → Ctrl + Shift + R
echo.
echo ========================================
echo.
echo  ขั้นตอนต่อไป:
echo  1. ✅ Clear Browser Cache (สำคัญ!)
echo  2. เข้าสู่ระบบ Odoo
echo  3. Settings ^> Apps
echo  4. ค้นหา "transport_booking"
echo  5. คลิก "Upgrade"
echo.
echo  ทดสอบ:
echo  1. เปิด Booking (state = done)
echo  2. แท็บ "⭐ ประเมินความพึงพอใจ"
echo  3. สร้าง Link ใหม่ + บันทึก
echo  4. คลิกปุ่ม "คัดลอก"
echo  5. Ctrl+V ที่ไหนก็ได้
echo  6. Link ปรากฏ! ✅
echo.
echo ========================================
pause
