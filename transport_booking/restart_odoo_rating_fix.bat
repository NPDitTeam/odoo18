@echo off
echo ========================================
echo  Restarting Odoo - Rating Feature Fix
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
echo  หรือ Activate Developer Mode แล้วใช้:
echo  Settings ^> Technical ^> Database Structure ^> Update Apps List
echo  แล้ว Upgrade module transport_booking
echo.
echo ========================================
pause
