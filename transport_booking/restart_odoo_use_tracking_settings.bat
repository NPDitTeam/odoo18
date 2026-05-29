@echo off
chcp 65001 > nul
echo ===============================================
echo   เปลี่ยนระบบให้ใช้ tracking.settings
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
echo ✅ ระบบใช้ tracking.settings แทน transport.user.settings
echo ✅ tracking_interval เป็นหน่วยนาที (default: 5 นาที)
echo ✅ แผนที่ติดตามการขนส่งจะอ่านค่าจาก tracking.settings
echo ✅ ชื่อฟิลด์ทั้งหมดเป็นภาษาไทย
echo.
pause
