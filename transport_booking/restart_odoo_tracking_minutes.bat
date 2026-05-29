@echo off
chcp 65001 > nul
echo ===============================================
echo   อัพเดทการตั้งค่าการติดตามเป็นนาที
echo ===============================================
echo.

echo หยุด Odoo Service...
net stop odoo-server-18.0

echo รอ 3 วินาที...
timeout /t 3 /nobreak > nul

echo เริ่ม Odoo Service พร้อมอัพเดทโมดูล...
"C:\Program Files\Odoo 18.0.20251009\python\python.exe" "C:\Program Files\Odoo 18.0.20251009\server\odoo-bin" ^
    -c "C:\Program Files\Odoo 18.0.20251009\server\odoo.conf" ^
    -u transport_booking ^
    -d vehicle_booking ^
    --stop-after-init

echo.
echo รอ 3 วินาที...
timeout /t 3 /nobreak > nul

echo เริ่ม Odoo Service ปกติ...
net start odoo-server-18.0

echo.
echo ===============================================
echo   เสร็จสิ้น!
echo ===============================================
echo.
echo การเปลี่ยนแปลง:
echo - tracking_interval เปลี่ยนจาก วินาที ^(30^) เป็น นาที ^(5^)
echo - ชื่อฟิลด์ทั้งหมดเป็นภาษาไทยแล้ว
echo - ชื่อเมนูเป็นภาษาไทยแล้ว
echo.
pause
