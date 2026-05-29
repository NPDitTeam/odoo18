# FIX COUNTDOWN TIMER - แก้ไขปัญหาการแสดงเวลารีเฟรชผิด

## ปัญหา
Countdown timer แสดง "รีเฟรชอีก 0 นาที 6 วินาที" แทนที่จะเป็น "รีเฟรชอีก 15 นาที 0 วินาที" เมื่อตั้งค่า tracking_interval เป็น 15 นาที

## สาเหตุ
ใน `tracking_map_food_delivery.xml` บรรทัด 776 มีการคำนวณ updateInterval ผิด:
```javascript
updateInterval = (userSettings.tracking_interval || 5) * 1000;
```

ควรเป็น:
```javascript
updateInterval = (userSettings.tracking_interval || 5) * 60 * 1000;
```

เพราะ `tracking_interval` เป็นหน่วย **นาที** แต่ตัวคำนวณขาด `* 60` ทำให้แปลงเป็น milliseconds ไม่ถูกต้อง

## วิธีแก้ไข

### ไฟล์ที่ต้องแก้: `views/tracking_map_food_delivery.xml`

ให้เปิดไฟล์และทำการแก้ไข **3 จุด**:

### จุดที่ 1: บรรทัด 776 (ภายใน loadUserSettings())
**จาก:**
```javascript
updateInterval = (userSettings.tracking_interval || 5) * 1000;
```

**เป็น:**
```javascript
// ✅ FIX: tracking_interval เป็นหน่วยนาที ต้องแปลงเป็น milliseconds ด้วย * 60 * 1000
updateInterval = (userSettings.tracking_interval || 5) * 60 * 1000;
```

### จุดที่ 2: บรรทัด 779 (console.log)
**จาก:**
```javascript
console.log(`⏱️  Update interval: ${updateInterval}ms`);
```

**เป็น:**
```javascript
console.log(`⏱️  Update interval: ${updateInterval}ms (${userSettings.tracking_interval} minutes)`);
```

### จุดที่ 3: บรรทัด 782 (settings badge)
**จาก:**
```javascript
document.getElementById('settingsBadge').textContent = 
    `⏱️ อัพเดททุก ${userSettings.tracking_interval}s`;
```

**เป็น:**
```javascript
document.getElementById('settingsBadge').textContent = 
    `⏱️ อัพเดททุก ${userSettings.tracking_interval} นาที`;
```

### จุดที่ 4: บรรทัด 793 (default badge in else)
**จาก:**
```javascript
document.getElementById('settingsBadge').textContent = 
    `⏱️ อัพเดททุก 5s (ค่าเริ่มต้น)`;
```

**เป็น:**
```javascript
document.getElementById('settingsBadge').textContent = 
    `⏱️ อัพเดททุก 5 นาที (ค่าเริ่มต้น)`;
```

### จุดที่ 5: บรรทัด 806 (catch error badge)
**จาก:**
```javascript
document.getElementById('settingsBadge').textContent = 
    `⏱️ อัพเดททุก 5s (ค่าเริ่มต้น)`;
```

**เป็น:**
```javascript
document.getElementById('settingsBadge').textContent = 
    `⏱️ อัพเดททุก 5 นาที (ค่าเริ่มต้น)`;
```

## ขั้นตอนการแก้ไข

1. เปิดไฟล์ด้วย text editor (Notepad++, VS Code, etc.)
```
C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking\views\tracking_map_food_delivery.xml
```

2. ใช้ Find & Replace (Ctrl+H) แก้ทั้ง 5 จุดตามด้านบน

3. บันทึกไฟล์

4. รัน `FIX_COUNTDOWN_TIMER.bat` เพื่อ restart Odoo

5. รีเฟรชหน้าแผนที่ติดตามในเบราว์เซอร์

## ผลลัพธ์ที่คาดหวัง

หลังจากแก้ไข countdown timer จะแสดง:
- "รีเฟรชอีก 15 นาที 0 วินาที" (สำหรับ tracking_interval = 15 นาที)
- Badge ด้านล่างแสดง: "⏱️ อัพเดททุก 15 นาที"
- แผนที่จะรีเฟรชทุก 15 นาที แทนที่จะเป็น 15 วินาที

## หมายเหตุ
- การแก้ไขนี้ทำให้ countdown timer และ update interval ใช้ค่า tracking_interval จาก tracking.settings อย่างถูกต้อง
- ไม่ต้องแก้ไขฐานข้อมูล เพราะค่าใน tracking.settings ถูกต้องอยู่แล้ว (เป็นหน่วยนาที)
- ปัญหาเกิดจากการแปลงหน่วยใน JavaScript เท่านั้น
