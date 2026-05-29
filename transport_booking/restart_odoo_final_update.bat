@echo off
echo ========================================
echo  Restarting Odoo - Final Updates
echo  1. ลบได้เฉพาะสถานะ "ร่าง"
echo  2. ซ่อนเมนู "ประเมินความพึงพอใจ"
echo  3. สร้าง Rating Link ต้องบันทึกก่อน
echo ========================================
echo.

REM Stop Odoo service
echo [1/3] Stopping Odoo service...
net stop odoo-server-18.0
timeout /t 3 /nobreak >nul

REM Start Odoo service
echo.
echo [2/3] Starting Odoo service...
net start odoo-server-18.0
timeout /t 5 /nobreak >nul

REM Open browser
echo.
echo [3/3] Opening Odoo in browser...
start http://localhost:8069

echo.
echo ========================================
echo  สำเร็จ! Odoo กำลังทำงานแล้ว
echo ========================================
echo.
echo  ขั้นตอนต่อไป:
echo  1. เข้าสู่ระบบ Odoo
echo  2. ไปที่ Settings ^> Apps
echo  3. ค้นหา "transport_booking"
echo  4. คลิก "Upgrade"
echo.
echo  ทดสอบ:
echo  - ลองลบ Booking สถานะ "ร่าง" (ลบได้)
echo  - ลองลบ Booking สถานะอื่นๆ (ลบไม่ได้)
echo  - สร้าง Rating Link (ต้องบันทึกเอง)
echo  - เมนู "ประเมินความพึงพอใจ" หายไป
echo.
echo ========================================
pause
