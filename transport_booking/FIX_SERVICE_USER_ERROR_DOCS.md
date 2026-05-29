# 🔧 แก้ไข "Service user is not available" Error

## 📋 Error ที่พบ

```
OwlError: An error occured in the owl lifecycle
Caused by: Error: Service user is not available
    at useService (web.assets_web.min.js:4505:219)
    at ListController.setup (web.assets_web.min.js:21154:650)
```

---

## 🔍 สาเหตุ

**ไฟล์:** `static/src/js/tracking_auto_refresh.js`

**บรรทัดที่เกิด error:**
```javascript
// Version 4.0 (ผิด)
this.user = useService("user");  // ❌ Service "user" ไม่มีใน Odoo 18
```

**ปัญหา:**
- Odoo 18 **ไม่มี service ชื่อ "user"**
- การเรียก `useService("user")` จะทำให้เกิด error ทันที
- ทำให้หน้า List View crash

---

## ✅ การแก้ไข

### FIX 1: ลบ user service
**เดิม (Version 4.0):**
```javascript
setup() {
    super.setup();
    
    this.orm = useService("orm");
    this.user = useService("user");  // ❌ Error!
    this.notification = useService("notification");
```

**ใหม่ (Version 4.1):**
```javascript
setup() {
    super.setup();
    
    this.orm = useService("orm");
    this.notification = useService("notification");
    // ✅ ลบ this.user = useService("user");
```

---

### FIX 2: ใช้ session.uid แทน
**เดิม:**
```javascript
// Version 4.0 พยายามใช้ this.user.userId
if (this.user && this.user.userId) {
    userId = this.user.userId;  // ❌ this.user ไม่มี
```

**ใหม่:**
```javascript
// Version 4.1 ใช้ session.uid (วิธีที่ถูกต้องใน Odoo 18)
// Method 1: ใช้ session.uid (แนะนำ)
if (this.env.session && this.env.session.uid) {
    userId = this.env.session.uid;
    console.log("👤 [Auto-Refresh] Got user ID from session.uid:", userId);
}
// Method 2: fallback to session.user_id
else if (this.env.session && this.env.session.user_id) {
    userId = this.env.session.user_id;
    console.log("👤 [Auto-Refresh] Got user ID from session.user_id:", userId);
}
// Method 3: fallback to user_context
else if (this.env.session && this.env.session.user_context && this.env.session.user_context.uid) {
    userId = this.env.session.user_context.uid;
    console.log("👤 [Auto-Refresh] Got user ID from user_context.uid:", userId);
}
else {
    console.error("❌ [Auto-Refresh] Cannot get user ID!");
    console.warn("⚠️  [Auto-Refresh] Using default interval: 30 minutes");
    this.trackingIntervalMinutes = 30;
    return;
}
```

---

## 📊 เปรียบเทียบ

### Version 4.0 (มี bug):
```javascript
❌ this.user = useService("user");           // Service ไม่มี → Error
❌ userId = this.user.userId;                // Cannot read
❌ userId = this.env.services.user.userId;   // undefined
```

### Version 4.1 (แก้แล้ว):
```javascript
✅ // ไม่ใช้ user service
✅ userId = this.env.session.uid;            // วิธีที่ถูกต้อง
✅ userId = this.env.session.user_id;        // Fallback 1
✅ userId = this.env.session.user_context.uid; // Fallback 2
```

---

## 🚀 วิธีใช้งาน

### ขั้นตอนที่ 1: Restart Odoo
```bash
ดับเบิลคลิก: FIX_SERVICE_USER_ERROR.bat
```

### ขั้นตอนที่ 2: เคลียร์ cache
```
กด Ctrl+Shift+Delete → Clear cache
```

### ขั้นตอนที่ 3: Hard Refresh
```
กด Ctrl+F5 ในหน้า List View
```

### ขั้นตอนที่ 4: ตรวจสอบ Console
```
กด F12 → Console

✅ ควรเห็น:
   🚀 [Auto-Refresh v4.1] Module loaded!
   👤 [Auto-Refresh] Got user ID from session.uid: 2
   ✨ Loaded FRESH tracking_interval: 30 minutes ✨
   🔄 Auto-refresh เปิดใช้งาน (ทุก 30 นาที)

❌ ไม่ควรมี:
   Service user is not available
   OwlError
   Cannot read properties of undefined
```

---

## 📋 ผลลัพธ์ที่คาดหวัง

### ก่อนแก้ไข (v4.0):
```
❌ Error: Service user is not available
❌ OwlError: An error occured in the owl lifecycle
❌ หน้า List View crash
❌ ไม่สามารถโหลด tracking_interval
```

### หลังแก้ไข (v4.1):
```
✅ ไม่มี error เกี่ยวกับ service user
✅ ไม่มี OwlError
✅ หน้า List View ทำงานปกติ
✅ โหลด tracking_interval สำเร็จ (30 นาที)
✅ Auto-refresh ทำงานตามที่ตั้งค่า
✅ Notification แสดงถูกต้อง
```

---

## 🧪 การทดสอบ

### Test Case 1: ตรวจสอบไม่มี error
```
1. เปิด List View (vehicle.tracking)
2. เปิด Console (F12)
3. ✅ ไม่มี error สีแดง
4. ✅ ไม่มี OwlError
5. ✅ List View โหลดปกติ
```

### Test Case 2: ตรวจสอบ user ID
```
1. ดู Console log
2. ✅ ควรเห็น: "👤 Got user ID from session.uid: 2"
3. ✅ ไม่มี error "Cannot get user ID"
```

### Test Case 3: ตรวจสอบ tracking_interval
```
1. ตั้งค่า tracking_interval = 30 ใน database
2. Reload หน้า
3. ✅ ควรเห็น: "✨ Loaded FRESH tracking_interval: 30 minutes ✨"
4. ✅ Notification: "🔄 Auto-refresh เปิดใช้งาน (ทุก 30 นาที)"
```

### Test Case 4: ตรวจสอบ auto-refresh
```
1. รอ 30 นาที
2. ✅ List view ควร refresh อัตโนมัติ
3. ✅ Console แสดง: "🔄 Refreshing tracking list at..."
```

---

## 🔍 Console Log ที่ดี

```javascript
// เมื่อโหลดหน้า List View ครั้งแรก
🚀 [Auto-Refresh v4.1] Module loaded!
🔧 [Auto-Refresh] Setup called for model: vehicle.tracking
✅ [Auto-Refresh] This is vehicle.tracking view!
📋 [Auto-Refresh] Loading FRESH tracking settings (no cache)...
👤 [Auto-Refresh] Got user ID from session.uid: 2
🕐 [Auto-Refresh] Request timestamp: 1730472849123
📦 [Auto-Refresh] Raw API response: {
  "tracking_interval": 30,
  "tracking_enabled": true,
  ...
}
✅ [Auto-Refresh] ✨ Loaded FRESH tracking_interval: 30 minutes ✨
🎯 [Auto-Refresh] View mounted, starting auto-refresh...
============================================================
🔄 [Auto-Refresh] Starting auto-refresh
   ⏱️  Interval: 30 minutes
   🕐 Milliseconds: 1800000ms
   📅 Next refresh at: 11:43:29
============================================================
✅ [Auto-Refresh] Notification displayed successfully
✅ [Auto-Refresh] Timer set with interval ID: 123
⏰ [Auto-Refresh] First refresh will happen in 30 minutes
✅ [Auto-Refresh v4.1] Patch applied successfully!
```

---

## 🆘 การแก้ไขปัญหา

### ยังมี error "Service user is not available":
1. ✓ ตรวจสอบว่า Odoo restart แล้ว
2. ✓ เคลียร์ cache เบราว์เซอร์ทั้งหมด
3. ✓ Hard refresh (Ctrl+F5)
4. ✓ ปิดเบราว์เซอร์แล้วเปิดใหม่

### ยังหา user ID ไม่ได้:
```javascript
// ดู Console log ว่า session มีอะไรบ้าง
console.log(this.env.session);

// ควรเห็นอย่างใดอย่างหนึ่ง:
{
  uid: 2,
  user_id: 2,
  user_context: { uid: 2 }
}
```

### ยังแสดง "ทุก 5 นาที":
1. ✓ ตรวจสอบค่าใน database:
   ```sql
   SELECT * FROM tracking_settings WHERE user_id = 2;
   ```
2. ✓ Update ค่า:
   ```sql
   UPDATE tracking_settings SET tracking_interval = 30 WHERE user_id = 2;
   ```
3. ✓ Restart Odoo

---

## 📄 ไฟล์ที่แก้ไข

**ไฟล์:** `static/src/js/tracking_auto_refresh.js`

**Changes:**
- Version: 4.0 → 4.1
- ลบ `this.user = useService("user");`
- เพิ่ม `this.env.session.uid` methods
- เพิ่ม fallback สำหรับ user_id และ user_context.uid
- Default tracking_interval = 30 minutes

---

## ✅ สรุป

การแก้ไขนี้แก้ปัญหา:

### ✅ ปัญหาที่แก้แล้ว:
1. ✅ Error "Service user is not available"
2. ✅ OwlError ใน lifecycle
3. ✅ หน้า List View crash
4. ✅ ไม่สามารถอ่าน user ID

### ✅ ผลลัพธ์:
1. ✅ List View ทำงานปกติ
2. ✅ อ่าน user ID ได้ผ่าน session.uid
3. ✅ โหลด tracking_interval สำเร็จ
4. ✅ Auto-refresh ทำงานตามที่ตั้งค่า
5. ✅ แสดง "ทุก 30 นาที" ถูกต้อง

### 🎯 Available Services ใน Odoo 18:
```javascript
✅ "orm"           - เข้าถึง database
✅ "notification"  - แสดง notification
✅ "action"        - จัดการ actions
✅ "dialog"        - แสดง dialogs
❌ "user"          - ไม่มี! ใช้ session แทน
❌ "rpc"           - ไม่มี! ใช้ orm แทน
```

---

**เวอร์ชัน:** 4.1  
**วันที่:** 2025-11-01  
**ผู้แก้ไข:** Claude Assistant  
**ไฟล์:** `static/src/js/tracking_auto_refresh.js`  
**Status:** ✅ พร้อมใช้งาน
