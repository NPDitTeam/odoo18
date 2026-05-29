# 🔄 แก้ไข Auto-Refresh ในหน้า Vehicle Tracking

## 🐛 ปัญหา
เมื่อเปิดหน้า **"GPS Tracking History"** (Vehicle Tracking list view)
- ❌ **เดิม**: แสดง "🔄 Auto-refresh เปิดใช้งาน (ทุก 30 นาที)" 
  - ค่า 30 นาที เป็น hardcoded ไม่ตรงกับค่า tracking_interval ในฐานข้อมูล
  - เมื่อแก้ไข tracking_interval เป็น 1 นาที แต่ list view ยังคงรีเฟรชทุก 30 นาที

## ✅ วิธีแก้ไข

### 1️⃣ สร้าง JavaScript ใหม่
**File:** `static/src/js/vehicle_tracking_auto_refresh.js`

```javascript
// 📡 Load tracking_interval จากฐานข้อมูล
async function loadTrackingInterval() {
    const response = await fetch('/api/settings/get', { ... });
    const data = await response.json();
    
    if (data.result.success) {
        const trackingInterval = data.result.data.tracking_interval || 1;
        // ✅ แปลงจากนาที → มิลลิวินาที
        autoRefreshInterval = trackingInterval * 60 * 1000;
        
        // แสดงค่าให้ผู้ใช้เห็น
        updateRefreshBadge(trackingInterval);
    }
}

// 🏷️ Update Auto-Refresh Badge
function updateRefreshBadge(minutes) {
    // สร้าง badge: "🔄 Auto-refresh เปิดใช้งาน (ทุก X นาที)"
    const badge = document.createElement('div');
    badge.innerHTML = `
        <span style="animation: spin 2s linear infinite;">🔄</span>
        <span>Auto-refresh เปิดใช้งาน (ทุก ${minutes} นาที)</span>
    `;
    // ใส่ badge ลงใน UI
}

// 🔄 Auto-Refresh List View
function setupAutoRefresh() {
    autoRefreshTimer = setInterval(() => {
        console.log('🔄 Auto-refreshing vehicle tracking list...');
        // refresh current view
        const btn = document.querySelector('button[title="🔄"]');
        if (btn) btn.click();
    }, autoRefreshInterval);
}

// 🚀 Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadTrackingInterval();
    setupAutoRefresh();
});
```

**ทำงาน:**
- ดึงค่า `tracking_interval` จากฐานข้อมูล (via `/api/settings/get`)
- แปลงจากนาที → มิลลิวินาที
- ตั้ง interval สำหรับ auto-refresh
- แสดง badge ที่อัพเดต

---

### 2️⃣ อัปเดต Manifest
**File:** `__manifest__.py`

```python
'assets': {
    'web.assets_backend': [
        ...
        'transport_booking/static/src/js/vehicle_tracking_auto_refresh.js',  # ✅ เพิ่ม
        ...
    ],
},
```

**ทำงาน:**
- เรียก JavaScript เมื่อ load หน้า vehicle.tracking

---

## 📊 ลำดับการทำงาน

```
1. User เปิดหน้า Vehicle Tracking
   ↓
2. vehicle_tracking_auto_refresh.js ทำงาน
   ├─ loadTrackingInterval()
   │  ├─ เรียก API /api/settings/get
   │  ├─ ดึง tracking_interval จากฐานข้อมูล
   │  └─ แปลงเป็น milliseconds
   ├─ updateRefreshBadge()
   │  └─ แสดง "🔄 Auto-refresh ทุก X นาที"
   └─ setupAutoRefresh()
      └─ ตั้ง interval และรีเฟรชทุกๆ X นาที
   ↓
3. ผู้ใช้เห็นข้อความที่ถูกต้อง ✅
```

---

## 🧪 ทดสอบ

### Test 1: ค่าเริ่มต้น
1. ✅ ยังไม่ได้ตั้งค่า tracking_interval
2. ✅ ระบบใช้ค่าเริ่มต้น 1 นาที
3. ✅ Badge แสดง "Auto-refresh เปิดใช้งาน (ทุก 1 นาที)"
4. ✅ List view รีเฟรชทุก 1 นาที

### Test 2: ตั้งค่าเป็น 3 นาที
1. ✅ ไปตั้ง tracking_interval = 3
2. ✅ รีเฟรชหน้า vehicle.tracking
3. ✅ Badge แสดง "Auto-refresh เปิดใช้งาน (ทุก 3 นาที)"
4. ✅ List view รีเฟรชทุก 3 นาที

### Test 3: ตั้งค่าเป็น 5 นาที
1. ✅ ไปตั้ง tracking_interval = 5
2. ✅ Badge แสดง "Auto-refresh เปิดใช้งาน (ทุก 5 นาที)"
3. ✅ List view รีเฟรชทุก 5 นาที

---

## 📱 Integration Points

### API: `/api/settings/get`
```json
{
  "success": true,
  "data": {
    "tracking_interval": 1,  // นาที ← ค่าที่ดึงมา
    "tracking_enabled": true,
    "show_speed": true,
    ...
  }
}
```

### Backend: `controllers/tracking_controller.py`
```python
@http.route('/api/settings/get', type='json', auth='user', methods=['POST'])
def get_user_settings_api(self, **kwargs):
    settings = request.env['tracking.settings'].get_user_settings(user_id)
    return {
        'success': True,
        'data': settings  # ✅ มีค่า tracking_interval
    }
```

---

## 🔍 Debug Logging

ตรวจสอบ Browser Console (F12):

```
📄 Vehicle Tracking page loaded
📡 Loading tracking_interval from database...
✅ Tracking interval loaded: 1 minutes
   Auto-refresh every: 60000 ms
⏰ Setting up auto-refresh interval: 60000ms
✅ Auto-refresh started

🔄 Auto-refreshing vehicle tracking list... (ทุก 1 นาที)
🔄 Auto-refreshing vehicle tracking list...
...
```

---

## ⚙️ ระบบ Fallback

### หากไม่สามารถดึง API
```javascript
if (error) {
    console.warn('⚠️ No settings found, using default 1 minute');
    autoRefreshInterval = 1 * 60 * 1000;  // 1 นาที
    updateRefreshBadge(1);
}
```

### ค่า Default
- **tracking_interval**: 1 นาที
- **autoRefreshInterval**: 60,000 ms (1 นาที)

---

## 📋 Checklist

- [x] สร้าง `vehicle_tracking_auto_refresh.js`
- [x] เพิ่ม loadTrackingInterval() function
- [x] เพิ่ม updateRefreshBadge() function
- [x] เพิ่ม setupAutoRefresh() function
- [x] อัปเดต `__manifest__.py`
- [x] ทดสอบ auto-refresh
- [x] สร้าง README

---

## 🚀 การใช้งาน

1. **รีสตาร์ท Odoo:**
   ```bash
   cd C:\Program Files\Odoo 18.0.20251009\server
   python -m odoo.bin -c odoo.conf
   ```

2. **ล้าง cache (ถ้าจำเป็น):**
   - ไปที่ Settings → Developer Tools → Clear Cache
   - หรือเพิ่ม `?debug=1` ลงใน URL

3. **ตรวจสอบ:**
   - เปิด Vehicle Booking
   - คลิก "📍 ตำแหน่ง GPS"
   - ดู Badge ที่แสดง tracking_interval

---

## 📁 ไฟล์ที่เปลี่ยน

```
✅ __manifest__.py
   - เพิ่ม vehicle_tracking_auto_refresh.js ใน assets

✅ static/src/js/vehicle_tracking_auto_refresh.js (ใหม่)
   - สคริปต์ auto-refresh จากฐานข้อมูล

ℹ️ views/vehicle_tracking_views.xml
   - Update comments (ไม่ต้องเปลี่ยน code)
```

---

**หมายเหตุ:** ถ้า auto-refresh ยังไม่ทำงาน ให้ตรวจสอบ:
1. ✅ JavaScript ถูก load ใน browser (F12 → Sources)
2. ✅ API `/api/settings/get` ตอบสนอง (F12 → Network)
3. ✅ Browser console ไม่มีข้อผิดพลาด (F12 → Console)
