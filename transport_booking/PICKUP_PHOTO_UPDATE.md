# 📸 รูปถ่ายสินค้าก่อนขนส่ง - Pickup Photo Display

## 🎯 การอัปเดต

เมื่อกดปุ่ม **"เริ่มงานขนส่ง"** ในแอป:

1. ✅ ถ่ายรูปสินค้า
2. ✅ ส่งรูปไปยัง Odoo18 (ฟิลด์ `pickup_photo`)
3. ✅ บันทึก `actual_pickup_time` (เวลาที่ถ่ายรูป)
4. ✅ แสดงรูปในแท็บ **"📍 ติดตามการขนส่ง"**

---

## 📋 การแสดงผลใน Odoo

### แท็บ "📍 ติดตามการขนส่ง" (เรียงจากบนลงล่าง)

```
┌─────────────────────────────────────────────────────┐
│ 📸 รูปถ่ายสินค้าก่อนขนส่ง                           │
│ ┌────────────────────────────────┐                  │
│ │                                │                  │
│ │      [รูปภาพขนาด 400x400]       │                  │
│ │                                │                  │
│ └────────────────────────────────┘                  │
│ เวลาที่ถ่ายรูป: 26/10/2025 11:09:00                │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 🗺️ แผนที่แสดงตำแหน่ง Real-time                     │
│ [iframe แสดงแผนที่]                                 │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 📍 จุดติดตาม GPS ทั้งหมด                           │
│ [ตารางแสดงจุด tracking]                            │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 📦 ข้อมูลการส่งมอบ                                  │
│ (แสดงเฉพาะเมื่อส่งของเสร็จ)                        │
│                                                     │
│ 📸 รูปถ่ายหลักฐานการส่ง   ✍️ ลายเซ็นผู้รับ         │
│ [รูป delivery_photo]       [รูป receiver_signature]│
└─────────────────────────────────────────────────────┘
```

---

## 🔧 ไฟล์ที่แก้ไข

### 1. `vehicle_booking_views.xml`

**เพิ่มส่วนแสดงรูป pickup_photo ที่ด้านบน:**

```xml
<page string="📍 ติดตามการขนส่ง" invisible="state == 'draft'">
    <!-- 📸 รูปถ่ายสินค้าก่อนขนส่ง - แสดงทันที -->
    <group string="📸 รูปถ่ายสินค้าก่อนขนส่ง" invisible="not pickup_photo">
        <field name="pickup_photo" widget="image" options="{'size': [400, 400]}" nolabel="1"/>
        <group>
            <field name="actual_pickup_time" string="เวลาที่ถ่ายรูป" readonly="1"/>
        </group>
    </group>
    
    <!-- ... ส่วนอื่นๆ ... -->
</page>
```

**จัดกลุ่มรูปการส่งมอบใหม่:**

```xml
<!-- รูปภาพการส่งมอบ (แสดงเฉพาะตอนส่งของเสร็จ) -->
<group invisible="not delivery_photo or not receiver_signature">
    <group string="📸 รูปถ่ายหลักฐานการส่ง" invisible="not delivery_photo">
        <field name="delivery_photo" widget="image" options="{'size': [400, 400]}" nolabel="1"/>
    </group>
    <group string="✍️ ลายเซ็นผู้รับ" invisible="not receiver_signature">
        <field name="receiver_signature" widget="image" options="{'size': [400, 200]}" nolabel="1"/>
    </group>
</group>
```

---

## 🔄 การทำงาน

### 1. ในแอป Mobile (start_job_screen.dart)

```dart
// ผู้ใช้ถ่ายรูปสินค้า
Future<void> _pickImage(ImageSource source) async {
  final XFile? image = await _picker.pickImage(
    source: source,
    maxWidth: 1920,
    maxHeight: 1080,
    imageQuality: 85,
  );
  // ...
}

// กดปุ่มเริ่มงาน - ส่งรูปไป Odoo
Future<void> _startJob() async {
  final success = await _odooService.startJobWithPhoto(
    bookingId: widget.booking.id,
    photoPath: _pickedImage!.path,  // 📸 รูปที่ถ่าย
  );
  // ...
}
```

### 2. ใน Odoo (vehicle_booking.py)

```python
def start_job_with_photo(self, photo_base64):
    """เริ่มงานพร้อมอัพโหลดรูปถ่ายสินค้า"""
    self.ensure_one()
    
    # บันทึกรูปถ่าย
    self.write({
        'pickup_photo': photo_base64,  # 📸 รูป base64
        'actual_pickup_time': fields.Datetime.now(),
    })
    
    # เริ่มงาน
    self.action_start()
    
    # สร้าง tracking record
    # ...
```

### 3. การแสดงผลใน Odoo

- **ก่อนเริ่มงาน (draft/confirmed):** ไม่มีรูป
- **หลังเริ่มงาน (in_progress):** แสดงรูป pickup_photo ที่ด้านบนของแท็บติดตาม
- **หลังส่งของเสร็จ (done):** แสดง pickup_photo + delivery_photo + receiver_signature

---

## 🧪 วิธีทดสอบ

### 1. รีสตาร์ท Odoo

เปิด Command Prompt **ในฐานะ Administrator**:

```batch
cd "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking"
restart_odoo_pickup_photo.bat
```

### 2. ทดสอบในแอป Mobile

```bash
cd C:\Users\theerapol\Downloads\npd_transport_app
flutter run
```

1. ล็อกอินด้วย PIN
2. เลือกงานที่ต้องการเริ่ม
3. กดปุ่ม **"เริ่มงาน"**
4. เลือก **"เปิดกล้องถ่ายรูป"** หรือ **"เลือกจากคลัง"**
5. ถ่าย/เลือกรูปสินค้า
6. กดปุ่ม **"🚚 เริ่มงานขนส่ง"**
7. รอจนเห็นข้อความ "✅ เริ่มงานและติดตามตำแหน่งสำเร็จ!"

### 3. ตรวจสอบใน Odoo18

1. เข้า: http://localhost:8078
2. Login: `Npd_admin` / `1234`
3. ไปที่: **จัดการการขนส่ง > การจองคิวรถขนส่ง**
4. เปิด booking ที่เพิ่งเริ่มงาน
5. คลิกแท็บ **"📍 ติดตามการขนส่ง"**
6. จะเห็น:
   - 📸 **รูปสินค้าที่ถ่าย** (ด้านบนสุด)
   - ⏰ **เวลาที่ถ่ายรูป**
   - 🗺️ แผนที่ tracking
   - 📍 จุด GPS

---

## 📊 ข้อมูลที่บันทึก

| ฟิลด์ | ประเภท | คำอธิบาย |
|-------|--------|----------|
| `pickup_photo` | Binary | รูปภาพ Base64 |
| `actual_pickup_time` | Datetime | เวลาที่รับสินค้า/ถ่ายรูป |
| `state` | Selection | เปลี่ยนเป็น `in_progress` |
| `tracking_status` | Selection | เปลี่ยนเป็น `in_transit` |

---

## 🎨 ข้อดีของ Layout ใหม่

1. ✅ **รูปแสดงชัดเจน** - อยู่ด้านบนสุด ไม่ซ่อน
2. ✅ **แยกส่วนชัดเจน** - pickup photo ≠ delivery photo
3. ✅ **แสดงเวลา** - รู้ว่ารับสินค้าเมื่อไหร่
4. ✅ **ขนาดเหมาะสม** - 400x400 pixels ดูชัดเจน
5. ✅ **จัดกลุ่มตรรกะ** - เริ่มงาน → tracking → ส่งของ

---

## 🐛 การแก้ปัญหา

### ❌ ไม่เห็นรูปใน Odoo

**สาเหตุ:**
1. รูปไม่ถูกส่งไป (ตรวจสอบ log ในแอป)
2. Odoo ไม่บันทึก (ตรวจสอบ log ใน Odoo)

**วิธีแก้:**
```python
# เช็ค log ใน Odoo
tail -f /var/log/odoo/odoo.log | grep "start_job_with_photo"

# ควรเห็น:
# ✅ [start_job_with_photo] Photo saved successfully
```

### ❌ รูปเบลอ/คุณภาพต่ำ

**วิธีแก้:** ปรับ quality ในแอป

```dart
final XFile? image = await _picker.pickImage(
  source: source,
  maxWidth: 1920,     // เพิ่มความละเอียด
  maxHeight: 1080,
  imageQuality: 90,   // เพิ่มคุณภาพ (85 → 90)
);
```

### ❌ Error: "ไม่สามารถเริ่มงานได้"

**วิธีแก้:**
1. ตรวจสอบ internet connection
2. ตรวจสอบ Odoo service ทำงานหรือไม่
3. ดู log error

---

## ✅ สรุป

การอัปเดตนี้ทำให้:

1. ✅ **รูปถ่ายสินค้า** ส่งไปยัง Odoo ได้สำเร็จ
2. ✅ **แสดงรูป** ในแท็บติดตามชัดเจน (ด้านบนสุด)
3. ✅ **บันทึกเวลา** ที่ถ่ายรูป
4. ✅ **แยกส่วน** pickup photo และ delivery photo
5. ✅ **Layout สวยงาม** และใช้งานง่าย

🎉 **พร้อมใช้งานแล้ว!**
