@echo off
echo ========================================
echo  Restarting Odoo - Unique Rating Fix
echo  1 Booking = 1 Rating Link เท่านั้น
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
echo  ================================
echo  1. Settings ^> Apps
echo  2. ค้นหา "transport_booking"
echo  3. คลิก "Upgrade"
echo     → Odoo จะสร้าง UNIQUE constraint
echo.
echo  วิธีทดสอบ:
echo  ================================
echo.
echo  A. สร้าง Rating Link ครั้งแรก:
echo     1. เปิด Booking (state = done)
echo     2. แท็บ "⭐ ประเมินความพึงพอใจ"
echo     3. คลิก "สร้าง Link ใหม่"
echo     4. ✅ เปิดฟอร์มใหม่
echo     5. บันทึก
echo     6. ✅ สร้างสำเร็จ
echo.
echo  B. พยายามสร้างซ้ำ:
echo     1. (Booking เดิม) คลิกปุ่มอีกครั้ง
echo     2. ✅ เปิด Rating Link เดิม
echo     3. Title: "... (มีอยู่แล้ว)"
echo     4. ❌ ไม่สร้างใหม่
echo.
echo  C. ทดสอบ Database Constraint:
echo     1. เปิด Rating Form
echo     2. Action ^> Duplicate
echo     3. บันทึก
echo     4. ❌ Error: "การจองนี้มี Link อยู่แล้ว!"
echo.
echo  ผลลัพธ์:
echo  ================================
echo  ✅ 1 Booking = 1 Rating Link เท่านั้น
echo  ✅ ไม่สามารถสร้าง Rating ซ้ำ
echo  ✅ คลิกซ้ำ → เปิด Rating เดิม
echo  ✅ Database บังคับให้ unique
echo.
echo ========================================
pause
