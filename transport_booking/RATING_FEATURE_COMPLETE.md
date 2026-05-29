# ✅ ระบบประเมินความพึงพอใจ - เสร็จสมบูรณ์

## 📋 สรุปฟีเจอร์
ระบบประเมินความพึงพอใจสำหรับงานขนส่งที่เสร็จสิ้นแล้ว โดยมีแท็บใหม่ "⭐ ประเมินความพึงพอใจ" ต่อจากแท็บ "📍 ติดตามการขนส่ง"

## 🎯 คุณสมบัติหลัก

### 1. แท็บประเมินความพึงพอใจ (⭐)
- **ตำแหน่ง**: แท็บที่ 3 ต่อจาก "📍 ติดตามการขนส่ง" 
- **เงื่อนไข**: แสดงเฉพาะเมื่องานขนส่งเสร็จสิ้นแล้ว (`state == 'done'`)
- **ฟีเจอร์**:
  - แสดงสถิติการประเมิน (จำนวนครั้ง, คะแนนล่าสุด)
  - สร้าง Link ประเมินใหม่
  - แสดงประวัติการประเมินทั้งหมด
  - คัดลอก Link สำหรับส่งให้ลูกค้า

### 2. ข้อมูลในการประเมิน
- **เลขที่จอง**: อ้างอิงจาก `booking_id.name`
- **ชื่อพนักงานขับรถ**: ดึงจาก `driver_id.name`
- **ข้อมูลเส้นทาง**: จุดรับ-ส่ง
- **ชื่อลูกค้า**: `partner_id.name`

### 3. ระบบ Rating Public Form
- **URL Format**: `https://[domain]/rating/[token]`
- **คุณสมบัติ**:
  - ไม่ต้อง Login
  - แสดงข้อมูลการจัดส่ง
  - ให้คะแนน 1-5 ดาว
  - แสดงข้อความตามคะแนน (แย่มาก - ดีมาก)
  - ช่องความคิดเห็นเพิ่มเติม
  - บันทึกวันที่ประเมิน
  - ป้องกัน Link ซ้ำ (One-time use)

## 📁 โครงสร้างไฟล์

### Models
```
transport_booking/models/
├── delivery_rating.py       # Model หลักสำหรับ Rating
└── vehicle_booking.py       # เพิ่ม relation กับ rating_ids
```

### Views
```
transport_booking/views/
├── delivery_rating_views.xml      # List/Form view สำหรับ backend
├── rating_templates.xml           # Public form templates
└── vehicle_booking_views.xml      # เพิ่มแท็บ ⭐ ประเมินความพึงพอใจ
```

### Controllers
```
transport_booking/controllers/
└── rating_controller.py           # Handle public rating submission
```

### Security
```
transport_booking/security/
└── ir.model.access.csv           # เพิ่ม permission สำหรับ delivery.rating
```

## 🔧 การติดตั้ง

### 1. อัปเดต Module
```bash
# วิธีที่ 1: ใช้ batch file
cd C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking
restart_odoo_rating.bat

# วิธีที่ 2: Restart Odoo Service ด้วยตนเอง
```

### 2. Upgrade Module
1. เข้า Odoo Settings → Apps
2. ค้นหา "transport_booking"
3. คลิก "Upgrade" 

## 💡 วิธีใช้งาน

### สร้าง Rating Link
1. เปิดการจองที่ `state == 'done'`
2. ไปที่แท็บ "⭐ ประเมินความพึงพอใจ"
3. คลิก "📝 สร้าง Link ประเมินใหม่"
4. คัดลอก Link และส่งให้ลูกค้า

### ตัวอย่าง Link
```
https://yourdomain.com/rating/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### สถานะ Rating
- **🟡 รอการประเมิน** (`pending`): สร้าง Link แล้ว รอลูกค้าประเมิน
- **🟢 ประเมินแล้ว** (`done`): ลูกค้าประเมินเรียบร้อยแล้ว
- **🔴 หมดอายุ** (`expired`): Link หมดอายุหรือถูกยกเลิก

## 📊 การแสดงผล

### Backend (Odoo)
```
แท็บ "⭐ ประเมินความพึงพอใจ"
│
├── สถิติการประเมิน
│   ├── จำนวนการประเมิน: 5
│   └── คะแนนล่าสุด: 4.5
│
├── ปุ่มสร้าง Link ใหม่
│
└── ประวัติการประเมินทั้งหมด
    ├── วันที่สร้าง Link
    ├── วันที่ประเมิน
    ├── สถานะ
    ├── คะแนน
    └── ความคิดเห็น
```

### Public Form (Customer)
```
หน้าประเมินความพึงพอใจ
│
├── ข้อมูลการจัดส่ง
│   ├── เลขที่จอง
│   ├── พนักงานขับรถ
│   ├── ชื่อลูกค้า
│   └── เส้นทาง (จุดรับ → ปลายทาง)
│
├── ให้คะแนน (1-5 ดาว)
│   ├── ⭐ แย่มาก
│   ├── ⭐⭐ แย่
│   ├── ⭐⭐⭐ ปานกลาง
│   ├── ⭐⭐⭐⭐ ดี
│   └── ⭐⭐⭐⭐⭐ ดีมาก
│
└── ความคิดเห็นเพิ่มเติม
```

## 🔐 Security & Permissions

### Access Rights
| Group | Read | Write | Create | Delete |
|-------|------|-------|--------|--------|
| User | ✅ | ✅ | ✅ | ❌ |
| Admin | ✅ | ✅ | ✅ | ✅ |
| Public | ✅ | ✅ | ❌ | ❌ |

**หมายเหตุ**: Public user สามารถอ่านและเขียน (submit rating) เท่านั้น ไม่สามารถสร้างหรือลบได้

## 📝 Database Fields

### delivery.rating
| Field | Type | Description |
|-------|------|-------------|
| booking_id | Many2one | เชื่อมกับการจอง |
| driver_id | Many2one | พนักงานขับรถ (related) |
| driver_name | Char | ชื่อพนักงาน (related) |
| rating_token | Char | Token สำหรับ public URL |
| rating_stars | Selection | คะแนน 1-5 |
| rating_value | Integer | คะแนนเป็นตัวเลข |
| customer_comment | Text | ความคิดเห็น |
| rating_date | Datetime | วันที่ประเมิน |
| created_date | Datetime | วันที่สร้าง Link |
| state | Selection | สถานะ (pending/done/expired) |

### vehicle.booking (เพิ่มเติม)
| Field | Type | Description |
|-------|------|-------------|
| rating_ids | One2many | รายการ rating ทั้งหมด |
| rating_count | Integer | จำนวนการประเมิน |
| latest_rating | Float | คะแนนล่าสุด |

## 🚀 API Endpoints

### Public Routes
```python
# แสดงฟอร์มประเมิน
GET /rating/<token>

# บันทึกการประเมิน (JSON-RPC)
POST /rating/submit
{
  "token": "...",
  "rating_stars": 5,
  "customer_comment": "บริการดีมาก"
}

# หน้าขอบคุณหลังประเมิน
GET /rating/success
```

## ✨ Features Highlight

### 1. Smart Button
- แสดงจำนวน Rating
- คลิกเพื่อดูประวัติทั้งหมด

### 2. One-Click Copy
- คัดลอก Link ได้ทันที
- แสดง notification พร้อม Link

### 3. Real-time Status
- สถานะอัปเดตทันทีเมื่อลูกค้าประเมิน
- แสดง Badge สีตามสถานะ

### 4. User-Friendly Public Form
- Responsive design
- ใช้งานง่ายบนมือถือ
- Interactive star rating
- Form validation

## 🎨 UI/UX Improvements
- 🌟 Star rating animation
- 📱 Mobile responsive
- 🎨 Bootstrap styling
- ✨ Smooth transitions
- 💬 Clear feedback messages

## 📞 Support & Contact
สำหรับคำถามหรือปัญหา กรุณาติดต่อ:
- Email: support@npdtransport.com
- Tel: 02-XXX-XXXX

---

**เวอร์ชัน**: 18.0.2.1.0  
**วันที่อัปเดต**: 26 ตุลาคม 2568  
**สถานะ**: ✅ เสร็จสมบูรณ์และพร้อมใช้งาน
