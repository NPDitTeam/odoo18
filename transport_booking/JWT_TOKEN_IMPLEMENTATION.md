# 🎯 NPD Transport Rating System - JWT Token Enhancement

## ✅ ที่แก้ไข

### 1. **Odoo Model** (`delivery_rating.py`)
✅ เพิ่ม JWT Token verification methods
✅ เก็บ JWT Token ในไฟล์ด้วย `jwt_token` field
✅ Method `get_rating_info()` รองรับทั้ง JWT + UUID Token
✅ Method `submit_rating()` รองรับทั้ง JWT + UUID Token

### 2. **PHP API** (`www/api_rating.php`)
✅ JWT Token สร้างและตรวจสอบ
✅ Token expiration (7 วัน)
✅ HMAC-SHA256 signature verification
✅ รองรับ Odoo 18 RPC API

### 3. **HTML Form** (ยังใช้เดิม - compatible)
✅ ดึง token จาก URL
✅ ส่ง token ไป PHP API

---

## 🚀 วิธีใช้งาน

### ขั้นตอนที่ 1: Restart Odoo
```bash
# ปิด Odoo ปัจจุบัน
# เปิด Odoo ใหม่เพื่อให้โหลด delivery_rating.py ตัวใหม่
```

### ขั้นตอนที่ 2: สร้าง Rating Link (ใน Odoo)
```
Delivery Booking → สร้าง Rating Link
→ ระบบจะสร้าง rating record + generate JWT Token
→ Link: https://npdhrms.com/odoo18/rating/TOKEN
```

### ขั้นตอนที่ 3: ลูกค้า Click Link
```
https://npdhrms.com/odoo18/rating/eyJhbGc...
→ HTML form ดึง token
→ เรียก api.php?action=get_rating&token=TOKEN
→ PHP ตรวจสอบ JWT signature + expiration
→ ดึงข้อมูล booking จาก Odoo
→ แสดงฟอร์มประเมิน
```

### ขั้นตอนที่ 4: ลูกค้า Submit Rating
```
POST api.php?action=submit_rating
Body: {
  "token": "JWT_TOKEN",
  "rating_stars": 5,
  "customer_comment": "ดีมากค่ะ"
}
→ PHP ตรวจสอบ JWT
→ บันทึก rating ลง Odoo
```

---

## 🔐 JWT Token Structure

```
Header.Payload.Signature

Header = {
  "alg": "HS256",
  "typ": "JWT"
}

Payload = {
  "booking_id": 123,
  "customer_email": "customer@example.com",
  "iat": 1700000000,
  "exp": 1700604800  # 7 วันหลังจากสร้าง
}

Signature = HMAC-SHA256(Header.Payload, JWT_SECRET)
```

---

## ⚠️ ต้องเปลี่ยน Secret Key

### ใน `delivery_rating.py`:
```python
JWT_SECRET = 'npd-transport-rating-secret-2024'  # ← เปลี่ยนค่านี้
```

### ใน `api_rating.php`:
```php
define('JWT_SECRET', 'npd-transport-rating-secret-2024');  // ← เปลี่ยนให้ตรงกับ Odoo
```

---

## 🧪 ทดสอบ

### 1. ทดสอบการสร้าง JWT Token
```python
# ใน Odoo Python Shell
from datetime import datetime
import json, base64, hmac, hashlib

rating = env['delivery.rating'].browse(1)
token = rating._create_jwt_token(123, 'test@example.com')
print(token)
```

### 2. ทดสอบการตรวจสอบ Token
```bash
# ผ่าน Postman หรือ curl
curl "http://localhost:8078/api_rating.php?action=verify_token&token=JWT_TOKEN"
```

### 3. ทดสอบการดึงข้อมูล Rating
```bash
curl "http://localhost:8078/api_rating.php?action=get_rating&token=JWT_TOKEN"
```

### 4. ทดสอบการบันทึก Rating
```bash
curl -X POST http://localhost:8078/api_rating.php?action=submit_rating \
  -H "Content-Type: application/json" \
  -d '{
    "token": "JWT_TOKEN",
    "rating_stars": 5,
    "customer_comment": "ดีมากค่ะ"
  }'
```

---

## 📝 Migration จาก UUID Token เป็น JWT

### เก่า (UUID Token):
```
Token: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### ใหม่ (JWT Token):
```
Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJib29raW5nX2lkIjoxMjMsImN1c3RvbWVyX2VtYWlsIjoiY3VzdG9tZXJAZXhhbXBsZS5jb20iLCJpYXQiOjE3MDAwMDAwMDAsImV4cCI6MTcwMDYwNDgwMH0...
```

### ✅ ระบบปัจจุบันรองรับทั้งสองแบบ:
- ถ้าส่ง JWT Token → ตรวจสอบ JWT
- ถ้าส่ง UUID Token → ใช้เดิม (backward compatible)

---

## 🔄 Flow Diagram

```
1. Delivery สร้าง Rating Link
   ↓
2. Odoo สร้าง JWT Token
   ↓
3. Send Email ให้ลูกค้า + Link
   ↓
4. ลูกค้า Click Link
   ↓
5. HTML form โหลด
   ↓
6. JavaScript ส่ง token ไป PHP API
   ↓
7. PHP ตรวจสอบ JWT signature + expiration
   ↓
8. ดึงข้อมูลจาก Odoo (ใช้ RPC)
   ↓
9. แสดงฟอร์ม
   ↓
10. ลูกค้า Input rating + comment
    ↓
11. ส่ง POST ไป PHP API
    ↓
12. PHP ตรวจสอบ JWT อีกครั้ง
    ↓
13. บันทึก rating ลง Odoo
    ↓
14. แสดง Success Page
```

---

## 🛠️ Troubleshooting

### ❌ Token expired
```
เหตุผล: Token เก่าเกิน 7 วัน
แก้ไข: สร้าง Rating Link ใหม่
```

### ❌ Token signature invalid
```
เหตุผล: JWT_SECRET ไม่ตรงกันระหว่าง Odoo + PHP
แก้ไข: เปลี่ยน JWT_SECRET ให้เหมือนกัน
```

### ❌ Invalid booking_id
```
เหตุผล: Booking ID ไม่ถูกต้อง
แก้ไข: ตรวจสอบ booking_id ในฐานข้อมูล
```

---

## 📊 ไฟล์ที่แก้ไข

| ไฟล์ | ตำแหน่ง | สิ่งที่เปลี่ยน |
|------|---------|-------------|
| `delivery_rating.py` | `models/` | JWT functions + updated methods |
| `api_rating.php` | `www/` | JWT verification + Odoo 18 integration |
| `index.html` | `/` | ยังใช้เดิม (compatible) |
| `rating_controller.py` | `controllers/` | ยังใช้เดิม |

---

## ✨ ประโยชน์ของ JWT Token

1. **ปลอดภัย**: HMAC-SHA256 signature verification
2. **ไม่ต้องเก็บ Database**: Self-contained token
3. **Expiration Built-in**: Token หมดอายุ 7 วัน
4. **Stateless**: ไม่ต้องเก็บ session server-side
5. **Backward Compatible**: ยังรองรับ UUID token เก่า

---

## 📞 Contact

สำหรับปัญหาใด ๆ ให้ตรวจสอบ logs:
```bash
C:\Program Files\Odoo 18.0.20251009\server\odoo.log
```
