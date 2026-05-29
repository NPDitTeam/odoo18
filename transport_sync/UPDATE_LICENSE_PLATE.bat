@echo off
chcp 65001 > nul
color 0A
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║     🔧 อัปเดต Module: transport_sync                         ║
echo ║     ✏️ แก้ไข: ฟิลด์ทะเบียนรถสามารถแก้ไขได้แล้ว              ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.
echo 📝 การเปลี่ยนแปลง:
echo    - license_plate_name: readonly=True → readonly=False
echo    - ✅ เพิ่ม tracking=True เพื่อติดตามการแก้ไข
echo.
echo 📋 ขั้นตอน:
echo    1. Stop Odoo Service
echo    2. Update Module transport_sync
echo    3. Restart Odoo Service
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
echo 🔄 Step 2: Update Module transport_sync...
echo ══════════════════════════════════════════════════════════════
cd "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin -c odoo.conf -d Tewtongdb -u transport_sync --stop-after-init

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
echo 📝 สิ่งที่เปลี่ยนแปลง:
echo    ✅ ฟิลด์ "ทะเบียนรถ" สามารถแก้ไขได้แล้ว
echo    ✅ ฟิลด์อื่นๆ ยังคง readonly ตามเดิม
echo    ✅ มีการติดตามการแก้ไข (tracking) ใน Chatter
echo.
echo 🌐 ทดสอบที่: http://localhost:8069
echo 📂 Menu: จัดการข้อมูลขนส่ง → ข้อมูลขนส่ง
echo 👤 Database: Tewtongdb
echo.
pause
