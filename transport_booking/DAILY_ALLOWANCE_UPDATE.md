# 📋 UPDATE: เพิ่มค่าเบี้ยเลี้ยง (Daily Allowance) ในระบบรายได้

## 📝 สรุปการแก้ไข

การแก้ไขนี้จะเพิ่ม **ค่าเบี้ยเลี้ยง (Daily Allowance)** ให้รวมในการคำนวณรายได้ของคนขับ
- เดิม: ค่าเที่ยว + ค่าขนส่ง
- ใหม่: ค่าเที่ยว + ค่าขนส่ง + **ค่าเบี้ยเลี้ยง**

---

## 🔧 ไฟล์ที่แก้ไข

### 1. **Odoo Backend** (ฝั่งเซิร์ฟเวอร์)

#### `models/delivery_history.py`
- ✅ เพิ่มฟิลด์ `daily_allowance` ในโมเดล `DeliveryHistory`
- ✅ อัปเดตฟังก์ชัน `create_from_booking()` ให้บันทึกค่าเบี้ยเลี้ยงจาก booking

**ตัวอย่างการทำงาน:**
```python
history_vals = {
    # ...
    'travel_expenses': booking.travel_expenses,       # ค่าเที่ยว
    'daily_allowance': booking.daily_allowance,       # ✅ ค่าเบี้ยเลี้ยง
    # ...
}
```

#### `views/delivery_history_views.xml`
- ✅ เพิ่มคอลัมน์ `travel_expenses` และ `daily_allowance` ในรายการ
- ✅ อัปเดต Form View ให้แสดงค่าเบี้ยเลี้ยง

**หน้า List View:**
```
เลขที่ | วันที่ | ลูกค้า | คนขับ | ค่าขนส่ง | ค่าเที่ยว | ค่าเบี้ยเลี้ยง | สถานะ
```

**หน้า Form View:**
```
ค่าใช้จ่าย:
├─ ค่าขนส่ง: 500 บาท
├─ ค่าเที่ยว: 100 บาท
└─ ค่าเบี้ยเลี้ยง: 200 บาท  ✅ NEW
```

### 2. **Flutter Mobile App** (ฝั่งแอปพลิเคชัน)

#### `lib/models/income_data.dart`
- ✅ เพิ่ม property `totalDailyAllowance`
- ✅ อัปเดต `totalIncome` getter:
  ```dart
  double get totalIncome => totalShippingCost + totalTravelExpenses + totalDailyAllowance;
  ```

#### `lib/services/odoo_service.dart` - ฟังก์ชัน `getMonthlyIncome()`
- ✅ อัปเดต `fields` ให้รวม `'daily_allowance'`
- ✅ ดึงค่าเบี้ยเลี้ยงจากการตอบสนองของ API
- ✅ รวมค่าเบี้ยเลี้ยงแต่ละรายการเข้าด้วยกัน

**ตัวอย่างโค้ด:**
```dart
'fields': ['completion_date', 'shipping_cost', 'travel_expenses', 'daily_allowance'],

// ดึงค่า
final dailyAllowance = record['daily_allowance'] != null
    ? (record['daily_allowance'] as num).toDouble()
    : 0.0;

// รวมค่าเบี้ยเลี้ยงสำหรับเดือน
incomeByMonth[monthKey] = IncomeData(
  // ...
  totalDailyAllowance: dailyAllowance,  // ✅
  // ...
);
```

#### `lib/screens/income_screen.dart`
- ✅ อัปเดต UI ให้แสดงค่าเบี้ยเลี้ยง
- ✅ ปรับปรุง Layout ให้แสดงรายละเอียด 3 รายการ:
  - 🚚 ค่าเที่ยว (สีน้ำเงิน)
  - 🍽️ ค่าเบี้ยเลี้ยง (สีส้ม) **✅ NEW**
  - 🚛 ค่าขนส่ง (สีเขียว)

**UI ตัวอย่าง:**
```
┌─────────────────────────────────┐
│ พฤศจิกายน 2568        [5 ครั้ง]│
├─────────────────────────────────┤
│ 🚛 ค่าขนส่ง    2,500.00 บาท    │
│ 🚗 ค่าเที่ยว      500.00 บาท    │
│ 🍽️ ค่าเบี้ยเลี้ยง 1,000.00 บาท   │ ✅ NEW
├─────────────────────────────────┤
│ รวมรายได้         4,000.00 บาท  │
└─────────────────────────────────┘
```

---

## 🚀 ขั้นตอนการใช้งาน

### Odoo Server
```bash
# 1. คัพ database (ทำให้แน่ใจ)
# 2. ก้อปไฟล์ที่แก้ไข
cp models/delivery_history.py /path/to/odoo/custom-addons/transport_booking/models/
cp views/delivery_history_views.xml /path/to/odoo/custom-addons/transport_booking/views/

# 3. Restart Odoo Server
# 4. Update module: Transport Booking Module
# 5. ล้าง Browser Cache (Ctrl+Shift+Delete)
```

### Flutter App
```bash
# 1. ก้อปไฟล์ที่แก้ไข
cp lib/models/income_data.dart /path/to/flutter/lib/models/
cp lib/services/odoo_service.dart /path/to/flutter/lib/services/
cp lib/screens/income_screen.dart /path/to/flutter/lib/screens/

# 2. รีบิลด์แอป
flutter clean
flutter pub get
flutter run
```

---

## ✅ การทดสอบ

### ทดสอบใน Odoo
1. เข้าไปในหน้า "ประวัติการจัดส่ง"
2. ตรวจสอบคอลัมน์ "ค่าเบี้ยเลี้ยง" ที่มีค่า
3. เปิด Record ที่เสร็จแล้ว
4. ตรวจสอบในแท็บ "ค่าใช้จ่าย" ว่ามี 3 ค่า:
   - ✅ ค่าขนส่ง
   - ✅ ค่าเที่ยว
   - ✅ ค่าเบี้ยเลี้ยง

### ทดสอบใน Mobile App
1. เข้าไปในหน้า "รายได้"
2. ตรวจสอบว่า "ค่าเบี้ยเลี้ยง" แสดงใน Card
3. ยืนยันว่า "รวมรายได้" รวมค่าเบี้ยเลี้ยง

---

## 🔐 ความปลอดภัย

- ✅ ไม่ได้แก้ไข SQL โดยตรง (ใช้ ORM)
- ✅ ไม่ได้แก้ไขไฟล์หลัก (manifest, __init__)
- ✅ ใช้การสื่อสารสอง Direction: Odoo → Mobile App
- ✅ ค่าเบี้ยเลี้ยงอ่านเฉพาะจาก vehicle_booking

---

## 📊 Impact Analysis

| ส่วน | ผลกระทบ | ความสำคัญ |
|------|--------|---------|
| **Odoo DB** | เพิ่มคอลัมน์ใหม่ | ⚠️ ต้อง Update Module |
| **API** | ส่งฟิลด์เพิ่มเติม | ✅ Backward Compatible |
| **Mobile App** | แสดงข้อมูลใหม่ | ✅ เพียง UI Update |
| **ประวัติ** | บันทึกค่าเบี้ยเลี้ยง | ✅ ตั้งแต่นี้ไป |

---

## 🆘 Troubleshooting

### ปัญหา: ค่าเบี้ยเลี้ยงไม่แสดงใน Mobile App

**วิธีแก้:**
1. ล้าง cache และ rebuild:
   ```bash
   flutter clean
   flutter pub get
   flutter run
   ```
2. ตรวจสอบ Odoo ว่า daily_allowance มีค่า
3. ดูใน Chrome DevTools ว่า API response มี daily_allowance

### ปัญหา: ค่า 0.0 ในคอลัมน์ daily_allowance

**วิธีแก้:**
1. ตรวจสอบ booking ว่า travel_expenses มีค่าจริงหรือไม่
2. ตรวจสอบวิธี create_from_booking ว่าส่งค่ามาถูกต้องหรือไม่

---

## 📝 Notes

- การแก้ไขนี้ **ไม่กระทบ** ข้อมูลเก่า
- ค่าเบี้ยเลี้ยง เก่าจะแสดงเป็น 0.0 (ถ้าไม่ได้บันทึก)
- ค่าเบี้ยเลี้ยง ใหม่จะบันทึกอัตโนมัติเมื่อเสร็จการจัดส่ง
