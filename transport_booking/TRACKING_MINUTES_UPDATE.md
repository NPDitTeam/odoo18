# สรุปการอัพเดทการตั้งค่าการติดตาม

## วันที่อัพเดท
1 พฤศจิกายน 2025

## การเปลี่ยนแปลงหลัก

### 1. เปลี่ยน tracking_interval จากวินาทีเป็นนาที

#### ก่อนแก้ไข:
```python
tracking_interval = fields.Integer('Tracking Interval (seconds)', default=30,
    help='ระยะเวลาในการส่งตำแหน่ง (วินาที)')
```

#### หลังแก้ไข:
```python
tracking_interval = fields.Integer('ช่วงเวลาการติดตาม (นาที)', default=5,
    help='ระยะเวลาในการส่งตำแหน่ง (นาที)')
```

**หมายเหตุ:** ค่า default เปลี่ยนจาก 30 วินาที เป็น 5 นาที (300 วินาที)

### 2. เปลี่ยนชื่อฟิลด์ทั้งหมดเป็นภาษาไทย

#### ฟิลด์ที่ได้รับการอัพเดท:

**การติดตามตำแหน่ง:**
- `tracking_enabled`: "Enable Tracking" → "เปิดการติดตาม"
- `tracking_interval`: "Tracking Interval (seconds)" → "ช่วงเวลาการติดตาม (นาที)"
- `high_accuracy`: "High Accuracy Mode" → "โหมดความแม่นยำสูง"

**การแจ้งเตือน:**
- `notify_on_arrival`: "Notify on Arrival" → "แจ้งเตือนเมื่อถึงจุดหมาย"
- `notify_on_delay`: "Notify on Delay" → "แจ้งเตือนเมื่อล่าช้า"
- `notify_off_route`: "Notify Off Route" → "แจ้งเตือนออกนอกเส้นทาง"
- `off_route_distance`: "Off Route Distance (meters)" → "ระยะออกนอกเส้นทาง (เมตร)"

**การแสดงผล:**
- `show_speed`: "Show Speed" → "แสดงความเร็ว"
- `show_route`: "Show Route" → "แสดงเส้นทาง"
- `map_type`: "Map Type" → "ประเภทแผนที่"
  - Options: "Roadmap" → "แผนที่ถนน", "Satellite" → "ภาพถ่ายดาวเทียม", "Hybrid" → "แบบผสม", "Terrain" → "แผนที่ภูมิประเทศ"

**การบันทึก:**
- `save_history`: "Save History" → "บันทึกประวัติ"
- `history_retention_days`: "History Retention (days)" → "เก็บประวัติ (วัน)"

### 3. อัพเดท View (tracking_settings_views.xml)

เพิ่ม `string` attributes สำหรับทุกฟิลด์เพื่อแสดงชื่อภาษาไทย:

```xml
<field name="tracking_enabled" string="เปิดการติดตาม"/>
<field name="tracking_interval" string="ช่วงเวลาการติดตาม (นาที)" invisible="not tracking_enabled"/>
<field name="high_accuracy" string="โหมดความแม่นยำสูง" invisible="not tracking_enabled"/>
<!-- และอื่นๆ -->
```

## ไฟล์ที่ได้รับการแก้ไข

1. `models/vehicle_tracking.py` - แก้ไข field definitions
2. `views/tracking_settings_views.xml` - เพิ่ม string attributes

## วิธีการติดตั้ง

รัน batch file:
```bash
restart_odoo_tracking_minutes.bat
```

หรือรันคำสั่งด้วยตัวเอง:
```bash
# หยุด Odoo
net stop odoo-server-18.0

# อัพเดทโมดูล
"C:\Program Files\Odoo 18.0.20251009\python\python.exe" ^
    "C:\Program Files\Odoo 18.0.20251009\server\odoo-bin" ^
    -c "C:\Program Files\Odoo 18.0.20251009\server\odoo.conf" ^
    -u transport_booking -d vehicle_booking --stop-after-init

# เริ่ม Odoo
net start odoo-server-18.0
```

## การใช้งาน

หลังจากอัพเดทแล้ว:

1. เข้าสู่ระบบ Odoo
2. ไปที่ Settings → Users & Companies → การตั้งค่าการติดตาม
3. จะเห็นว่า "ช่วงเวลาการติดตาม" แสดงเป็นนาที
4. ค่า default คือ 5 นาที

## หมายเหตุสำคัญ

⚠️ **สำหรับข้อมูลเก่า:**
- ข้อมูลที่มีอยู่แล้วในฐานข้อมูลจะยังคงเป็นหน่วยวินาที
- ถ้ามีการตั้งค่าเดิมอยู่ (เช่น 30 วินาที) ระบบจะตีความเป็น 30 นาที
- แนะนำให้ตรวจสอบและปรับค่าใหม่หลังอัพเดท

⚠️ **สำหรับ API/Frontend:**
- ต้องอัพเดท code ที่ใช้ tracking_interval ให้แปลงหน่วยเป็นนาที
- ถ้ามีการคำนวณเป็นวินาที ต้องคูณด้วย 60

## การทดสอบ

1. ✅ ตรวจสอบว่าฟิลด์แสดงเป็นภาษาไทย
2. ✅ ตรวจสอบว่าค่า default เป็น 5 นาที
3. ✅ ตรวจสอบว่า help text แสดงถูกต้อง
4. ✅ ตรวจสอบว่าเมนูเป็นภาษาไทย
5. ⚠️ ทดสอบการส่งข้อมูล tracking ด้วย interval ใหม่

## ติดต่อ

หากมีปัญหาหรือข้อสงสัย กรุณาติดต่อผู้พัฒนาระบบ
