@echo off
chcp 65001 > nul
color 0A
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║     🔧 อัปเดต: เปลี่ยนหน่วยติดตามจากวินาทีเป็นนาที          ║
echo ║     💰 เพื่อประหยัดค่าใช้จ่าย Google Maps API                ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo 📝 การเปลี่ยนแปลง:
echo    🔄 หน่วย: วินาที → นาที
echo    ⏰ Default: 30 วินาที → 2 นาที
echo    📊 Validation: 5-300 วินาที → 1-60 นาที
echo    💵 ประโยชน์: ลด API calls ลง 24 เท่า (จาก 12 ครั้ง/นาที → 0.5 ครั้ง/นาที)
echo.
echo 📋 ไฟล์ที่แก้ไข:
echo    - models/res_users_settings.py
echo    - views/tracking_map_template.xml
echo    - views/tracking_map_modern.xml  
echo    - views/tracking_map_food_delivery.xml
echo.
pause

echo.
echo ══════════════════════════════════════════════════════════════
echo 🛑 Step 1: Stopping Odoo Service...
echo ══════════════════════════════════════════════════════════════
net stop odoo-server-18.0
timeout /t 3 > nul

echo.
echo ══════════════════════════════════════════════════════════════
echo 🔄 Step 2: Update Module transport_booking...
echo ══════════════════════════════════════════════════════════════
cd "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin -c odoo.conf -d Tewtongdb -u transport_booking --stop-after-init

echo.
echo ══════════════════════════════════════════════════════════════
echo ▶️ Step 3: Restart Odoo Service...
echo ══════════════════════════════════════════════════════════════
net start odoo-server-18.0

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║              ✅ เสร็จสิ้น! Complete                          ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo 📝 สรุปการเปลี่ยนแปลง:
echo    ✅ เปลี่ยนหน่วยจาก วินาที เป็น นาที
echo    ✅ Default ใหม่: 2 นาที (120,000 มิลลิวินาที)
echo    ✅ แก้ไข Template ทั้ง 3 ไฟล์
echo    ✅ อัปเดต Validation (1-60 นาที)
echo.
echo 💰 ประโยชน์:
echo    - ลดการเรียก Google Maps API ลง 24 เท่า
echo    - ประหยัดค่าใช้จ่ายบริษัท
echo    - ยังคงความแม่นยำในการติดตาม
echo.
echo 🌐 ทดสอบที่: http://localhost:8069
echo 📂 Menu: จองคิวรถขนส่ง → การตั้งค่า
echo 👤 Database: Tewtongdb
echo.
pause
