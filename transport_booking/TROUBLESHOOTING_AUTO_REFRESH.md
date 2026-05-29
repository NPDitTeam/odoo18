# 🔧 แก้ปัญหา Auto-Refresh ไม่ขึ้น

## ปัญหา
- ไม่เห็น notification "🔄 Auto-refresh เปิดใช้งาน"
- ค่ายังแสดง 5 นาที แทนที่จะเป็น 30 นาที
- List ไม่ refresh อัตโนมัติ

## ✅ วิธีแก้ไขทีละขั้นตอน

### Step 1: ตรวจสอบค่าใน Odoo

1. Login เข้า Odoo
2. ไปที่เมนู **Settings** หรือที่คุณสร้าง tracking settings ไว้
3. เช็คว่า **"ช่วงเวลาการติดตาม (นาที)"** = **30** จริงหรือไม่
4. กด **Save** อีกครั้ง (แม้จะบันทึกแล้ว)

### Step 2: Upgrade Module

**นี่คือสาเหตุหลัก!** JavaScript file ใหม่ไม่ถูก load จนกว่าจะ upgrade module

1. ไปที่ **Settings** > **Apps**
2. ลบ filter "Apps" (คลิก X)
3. ค้นหา "**transport_booking**"
4. คลิก **⋮** (3 จุด) > **Upgrade**
5. รอจนกว่าจะเสร็จ

### Step 3: Clear Browser Cache

1. กด **Ctrl + Shift + Delete**
2. เลือก:
   - ✅ Cached images and files
   - ✅ Cookies and other site data
3. เลือกช่วงเวลา: **All time**
4. คลิก **Clear data**

### Step 4: Logout และ Login ใหม่

1. **Logout** จาก Odoo
2. **ปิดเบราว์เซอร์** ทั้งหมด
3. **เปิดเบราว์เซอร์ใหม่**
4. **Login** เข้า Odoo อีกครั้ง

### Step 5: ทดสอบและตรวจสอบ

1. เปิด **Browser Console** (กด **F12**)
2. ไปที่ tab **Console**
3. เปิด Vehicle Booking
4. คลิกปุ่ม **"📍 ตำแหน่ง GPS"**

### Step 6: ดู Console Output

ถ้าทุกอย่างทำงานถูกต้อง คุณควรเห็น:

```
🚀 [Auto-Refresh] Module loaded!
🔧 [Auto-Refresh] Setup called for model: vehicle.tracking
✅ [Auto-Refresh] This is vehicle.tracking view!
📋 [Auto-Refresh] Loading tracking settings from database...
👤 [Auto-Refresh] Current user ID: 2
📦 [Auto-Refresh] Settings received: {tracking_interval: 30, ...}
✅ [Auto-Refresh] Loaded tracking_interval: 30 minutes
🎯 [Auto-Refresh] View mounted, starting auto-refresh...
🔄 [Auto-Refresh] Starting auto-refresh every 30 minutes (1800000ms)
✅ [Auto-Refresh] Notification displayed
✅ [Auto-Refresh] Timer set with interval ID: 123
✅ [Auto-Refresh] Patch applied successfully!
```

## 🔍 การตรวจสอบปัญหา

### ถ้าไม่เห็นข้อความใน Console เลย

**สาเหตุ:** Module ยังไม่ได้ upgrade หรือ JavaScript ไม่ถูก load

**วิธีแก้:**
1. ย้อนกลับไปทำ **Step 2** (Upgrade Module) อีกครั้ง
2. ตรวจสอบว่า `__manifest__.py` มี JavaScript file หรือไม่:
   ```
   cd "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking"
   type __manifest__.py | findstr tracking_auto_refresh
   ```
   ควรเห็น: `'transport_booking/static/src/js/tracking_auto_refresh.js'`

### ถ้าเห็น "⏭️ [Auto-Refresh] Skipping"

**สาเหตุ:** เปิด list view ผิด model (ไม่ใช่ vehicle.tracking)

**วิธีแก้:**
- ตรวจสอบว่าคุณเปิดจากปุ่ม **"📍 ตำแหน่ง GPS"** จริงหรือไม่
- อย่าเปิดจากเมนูอื่น

### ถ้าเห็น "⚠️ No tracking_interval in settings"

**สาเหตุ:** ค่า tracking_interval ไม่ได้ส่งมาจาก API

**วิธีแก้:**
1. เช็คว่ามี tracking.settings ในฐานข้อมูลหรือไม่
2. ไปที่ Odoo > Settings > ตั้งค่า tracking_interval อีกครั้ง
3. Save และ Logout/Login ใหม่

### ถ้าค่ายังเป็น 5 นาที

**สาเหตุ:** Session เก่ายัง cache ค่าเดิมไว้

**วิธีแก้:**
1. **Logout** จาก Odoo
2. **ปิดเบราว์เซอร์** ทั้งหมด
3. Clear browser cache
4. **เปิดเบราว์เซอร์ใหม่** และ Login ใหม่

## 🔧 วิธีตรวจสอบขั้นสูง

### เช็คว่า JavaScript file ถูก load

1. เปิด Browser Console (F12)
2. ไปที่ tab **Sources** (หรือ **Debugger**)
3. กด **Ctrl+P** (Quick Open)
4. พิมพ์: `tracking_auto_refresh`
5. ควรเห็นไฟล์นี้ใน list

ถ้าไม่เจอ = Module ยังไม่ได้ upgrade!

### ตรวจสอบค่าใน Database (Advanced)

รัน query นี้ใน pgAdmin หรือ psql:

```sql
SELECT 
    ts.id,
    ru.login,
    ts.tracking_interval
FROM tracking_settings ts
LEFT JOIN res_users ru ON ts.user_id = ru.id;
```

ควรเห็นค่า `tracking_interval = 30`

## 📝 Checklist ก่อนเปิดตั๋ว Support

- [ ] ✅ Module upgrade แล้ว (Settings > Apps > Upgrade)
- [ ] ✅ Clear browser cache แล้ว
- [ ] ✅ Logout/Login ใหม่แล้ว
- [ ] ✅ เปิด Browser Console (F12) และดู log
- [ ] ✅ เช็คว่า tracking_interval = 30 ในหน้าตั้งค่า
- [ ] ✅ เปิดจากปุ่ม "📍 ตำแหน่ง GPS" (ไม่ใช่เมนูอื่น)

## 🚀 วิธีการแก้ไขที่รวดเร็วที่สุด

ถ้าอยากให้มันใช้งานได้เลย ทำตามนี้:

```batch
REM 1. Restart Odoo
net stop odoo-server-18.0
timeout /t 3
net start odoo-server-18.0
```

หลังจาก Odoo restart:

1. Login เข้า Odoo
2. Settings > Apps > ลบ filter > ค้นหา "transport_booking" > Upgrade
3. Logout
4. Clear browser cache (Ctrl+Shift+Del)
5. ปิดเบราว์เซอร์
6. เปิดเบราว์เซอร์ใหม่
7. Login
8. ทดสอบ

## 🎯 Expected Result

หลังทำตามขั้นตอนข้างต้น:

✅ เห็น notification "🔄 Auto-refresh เปิดใช้งาน (ทุก 30 นาที)"  
✅ Console log แสดง "Loaded tracking_interval: 30 minutes"  
✅ List refresh ทุก 30 นาที  

---

**หมายเหตุ:** ถ้ายังไม่ได้ ให้แนบ screenshot ของ:
1. Browser Console (F12 > Console tab)
2. หน้า tracking settings ที่แสดงค่า 30 นาที
3. หน้า Apps ที่แสดงว่า module upgrade แล้ว
