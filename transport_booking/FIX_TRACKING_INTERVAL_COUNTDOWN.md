# 🔧 แก้ไข Countdown Timer - ดึงค่า tracking_interval จากฐานข้อมูล

## 📋 ปัญหาที่แก้ไข

เมื่อคลิกปุ่ม **"📍 ตำแหน่ง GPS"** (action_view_tracking) ใน Web UI:
- ❌ **เดิม**: Countdown timer ใช้ค่า hardcoded 1 นาที ไม่ตรงกับค่า tracking_interval ในฐานข้อมูล
- ✅ **ใหม่**: ดึงค่า `tracking_interval` จากตาราง `tracking.settings` โดยตรง

## 📝 ไฟล์ที่แก้ไข

### 1. **Backend - models/vehicle_booking.py** (บรรทัด 617)
```python
def action_view_tracking(self):
    """เปิดดู tracking records ของ booking นี้พร้อมแสดง countdown timer จากค่า tracking_interval"""
    
    # ✅ ดึงค่า tracking_interval จากตาราง tracking.settings
    settings = self.env['tracking.settings'].search([
        ('user_id', '=', self.env.user.id)
    ], limit=1)
    
    if not settings:
        settings = self.env['tracking.settings'].create({
            'user_id': self.env.user.id,
            'tracking_interval': 1  # ค่าเริ่มต้น 1 นาที
        })
    
    # เตรียมข้อมูล countdown timer
    tracking_interval_seconds = (settings.tracking_interval or 1) * 60
    
    # ✅ ส่งค่า tracking_interval ไปใน context
    return {
        'context': {
            'tracking_interval': settings.tracking_interval,
            'tracking_interval_seconds': tracking_interval_seconds,
        }
    }
```

**การเปลี่ยนแปลง:**
- ดึง `tracking.settings` record ของ user ปัจจุบัน
- คำนวณ `tracking_interval_seconds` แล้วส่งไปใน context
- Logging ข้อมูลสำหรับ debug

---

### 2. **Controller - controllers/tracking_controller.py** (บรรทัด 53)
```python
# ดึง tracking_interval จาก tracking.settings
settings_model = request.env['tracking.settings']
user_settings = settings_model.get_user_settings(request.env.user.id)
refresh_interval = user_settings.get('tracking_interval', 1)  # ✅ ค่าเริ่มต้น 1 นาที
```

**การเปลี่ยนแปลง:**
- เปลี่ยนค่าเริ่มต้นจาก 5 นาที → **1 นาที**
- ดึงจาก `tracking.settings` อย่างสม่ำเสมอ
- ส่งค่านี้ไปยัง template เป็น `refresh_interval`

---

### 3. **Frontend - views/tracking_map_food_delivery.xml** (บรรทัด 330-335)
```javascript
// ⚙️ Configuration
const CONFIG = {
    bookingId: [booking.id],
    refreshIntervalMinutes: [refresh_interval],  // ✅ ดึงจาก tracking.settings
    defaultUpdateInterval: [refresh_interval * 60 * 1000],  // แปลงเป็น milliseconds
};
```

**การเปลี่ยนแปลง:**
- ใช้ค่า `refresh_interval` จาก template (ที่ส่งจาก controller)
- แปลงเป็น milliseconds สำหรับ JavaScript timer
- Fallback ใช้ค่านี้ถ้า API ไม่ตอบ

---

### 4. **Frontend JavaScript - loadUserSettings()** (บรรทัด 759-808)
```javascript
async function loadUserSettings() {
    // ดึงจาก API
    const intervalMinutes = userSettings.tracking_interval || CONFIG.refreshIntervalMinutes;
    updateInterval = intervalMinutes * 60 * 1000;
    
    // ✅ แสดง settings badge
    document.getElementById('settingsBadge').textContent = 
        `⏱️ อัพเดททุก ${intervalMinutes} นาที (จากฐานข้อมูล)`;
}
```

**การเปลี่ยนแปลง:**
- ใช้ค่า `CONFIG.refreshIntervalMinutes` เป็น default
- แสดงค่า tracking_interval ใน settings badge
- Log ข้อมูลสำหรับ debug

---

## 🚀 วิธีใช้

### ตั้งค่า tracking_interval
1. ไปที่ **ระบบติดตามรถ → ตั้งค่าการติดตาม**
2. ค้นหา record ของ user ปัจจุบัน
3. แก้ไข field **"Tracking Interval (Minutes)"** เป็นค่าที่ต้องการ (เช่น 2, 3, 5 นาที)
4. บันทึก

### ดูผล
1. เปิด Vehicle Booking form
2. คลิกปุ่ม **"📍 ตำแหน่ง GPS"**
3. Countdown timer จะแสดงค่าตามที่ตั้งไว้ในฐานข้อมูล
4. ตรวจสอบ **"⏱️ Settings Badge"** ที่ด้านล่างขวา

---

## 📊 ลำดับการทำงาน

```
1. User คลิกปุ่ม "📍 ตำแหน่ง GPS"
   ↓
2. action_view_tracking() ทำงาน
   ├─ ดึง tracking.settings ของ user
   ├─ คำนวณ tracking_interval_seconds
   └─ ส่งไปใน context
   ↓
3. Controller: tracking_map_view()
   ├─ ดึง refresh_interval จาก tracking.settings
   └─ ส่งไปยัง template เป็น "refresh_interval"
   ↓
4. Frontend Template
   ├─ CONFIG.refreshIntervalMinutes = refresh_interval (จากการทำงาน #3)
   └─ CONFIG.defaultUpdateInterval = refreshIntervalMinutes * 60 * 1000
   ↓
5. JavaScript
   ├─ initMap() → loadUserSettings()
   ├─ ดึงจาก API /api/settings/get
   ├─ updateInterval = (tracking_interval หรือ CONFIG.refreshIntervalMinutes) * 60 * 1000
   ├─ startCountdownTimer() → startAutoUpdate()
   └─ Countdown timer นับถอยหลัง
```

---

## 🧪 การทดสอบ

### Test 1: ค่าเริ่มต้น (1 นาที)
- ❌ ยังไม่ได้ตั้งค่า tracking_interval
- ✅ ระบบสร้าง tracking.settings ใหม่ด้วยค่า 1 นาที
- ✅ Countdown timer แสดง "รีเฟรชอีก 1 นาที 0 วินาที"

### Test 2: ตั้งค่าเป็น 3 นาที
- ✅ ไปตั้ง tracking_interval = 3
- ✅ Countdown timer แสดง "รีเฟรชอีก 3 นาที 0 วินาที"
- ✅ นับถอยหลังจนถึง 0 แล้ว reset กลับเป็น 3 นาที

### Test 3: API Error Fallback
- ✅ ปิด API endpoint ชั่วคราว
- ✅ JavaScript ใช้ CONFIG.refreshIntervalMinutes (default 1 นาที)
- ✅ Countdown timer ยังคงทำงาน

---

## 📱 App Mobile Integration

App ที่ดึง `tracking_interval` จาก API `/api/settings/get` จะได้รับค่าเดียวกัน:
```json
{
  "success": true,
  "data": {
    "tracking_interval": 1,  // นาที
    "tracking_enabled": true,
    "show_speed": true,
    ...
  }
}
```

---

## 🔍 Debug Logging

ดู Odoo logs เพื่อตรวจสอบ:
```
🗺️ [Map] Loading map for booking SO/002
⏱️  [Map] Refresh Interval: 1 minutes
👤 [Map] Driver: นาย ก
📍 [Action] Opening tracking view for SO/002
⏱️  [Action] tracking_interval from DB: 1 minutes (60 seconds)
```

---

## ✅ Checklist

- [x] แก้ไข `action_view_tracking()` ใน vehicle_booking.py
- [x] แก้ไข controller tracking_map_view()
- [x] แก้ไข template CONFIG.refreshIntervalMinutes
- [x] แก้ไข loadUserSettings() ใช้ค่า default
- [x] ทดสอบ countdown timer
- [x] ทดสอบ API fallback
- [x] สร้าง README documentation

---

**หมายเหตุ:** ต้องรีสตาร์ท Odoo Server เพื่อให้การแก้ไขมีผล
