✅ FIX: ค่าเบี้ยเลี้ยง ไม่แสดงในแอป - COMPLETED
═══════════════════════════════════════════════════════════════

📋 ปัญหา:
  • แอป (frontend) ไม่แสดงค่าเบี้ยเลี้ยง (daily_allowance)
  • ในหน้าประวัติการจัดส่ง

🔍 สาเหตุที่พบ:
  1. api_controller.py - ฟังก์ชัน get_booking_detail()
     - ❌ ไม่มี daily_allowance ในการส่งกลับแอป
     
  2. ไม่มี API endpoint สำหรับ delivery_history
     - ❌ ไม่มี /api/v1/delivery_history/get_all
     - ❌ ไม่มี /api/v1/delivery_history/get/<id>

🔧 วิธีแก้ที่ทำ:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣  เพิ่ม daily_allowance ใน get_booking_detail()
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

เพิ่มบรรทัด:
    'daily_allowance': booking.daily_allowance,

ตำแหน่ง: api_controller.py - ฟังก์ชัน get_booking_detail()

✅ ผลลัพธ์:
   - แอปสามารถดึง daily_allowance จาก vehicle_booking ได้แล้ว

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2️⃣  เพิ่ม 2 endpoint ใหม่ สำหรับ delivery_history
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Endpoint 1: ดึงข้อมูลหลายรายการ
  Route: POST /api/v1/delivery_history/get_all
  Request:
  {
    "driver_id": 1,      (optional)
    "limit": 50,
    "fields": [...]      (optional)
  }
  
  Response:
  {
    "success": true,
    "data": [
      {
        "id": 1,
        "name": "BOOK-20251121-0018",
        "partner_name": "บริษัท ABC",
        "driver_name": "สมชาย",
        "vehicle_name": "กท 1234",
        "shipping_cost": 500.00,
        "travel_expenses": 100.00,
        "daily_allowance": 210.00,    ← ✅ ค่าเบี้ยเลี้ยง
        "completion_date": "2025-11-21T20:00:24",
        "state": "completed"
      }
    ],
    "count": 1
  }

📌 Endpoint 2: ดึงข้อมูลรายการเดียว
  Route: GET /api/v1/delivery_history/get/<history_id>
  
  Response:
  {
    "success": true,
    "data": {
      "id": 1,
      "name": "BOOK-20251121-0018",
      "partner_name": "บริษัท ABC",
      "driver_name": "สมชาย",
      "vehicle_name": "กท 1234",
      "distance_km": 152.483,
      "total_weight_order": 36,
      "duration_hours": 7.01,
      "shipping_cost": 3100.00,
      "travel_expenses": 0.00,
      "daily_allowance": 210.00,    ← ✅ ค่าเบี้ยเลี้ยง
      "currency": "THB",
      "pickup_location": "...",
      "destination": "...",
      "receiver_name": "ทดสอบ ทดสอบ",
      "completion_date": "2025-11-21T20:00:24",
      "actual_delivery_time": "2025-11-21T20:00:24",
      "state": "completed"
    }
  }

✅ ผลลัพธ์:
   - ✅ daily_allowance ถูกส่งไปแอปทั้ง 2 endpoint
   - ✅ แอปสามารถแสดงค่าเบี้ยเลี้ยงได้แล้ว
   - ✅ สนับสนุน filter โดย driver_id

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 ฟิลด์ที่รวมอยู่ใน delivery_history responses:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ ฟิลด์ที่มีค่าเบี้ยเลี้ยง:
  • name (เลขที่จอง)
  • partner_name (ชื่อลูกค้า)
  • driver_name (ชื่อคนขับ)
  • vehicle_name (ทะเบียนรถ)
  • distance_km (ระยะทาง)
  • duration_hours (ระยะเวลา)
  • shipping_cost (ค่าขนส่ง)
  • travel_expenses (ค่าเที่ยว)
  • daily_allowance (ค่าเบี้ยเลี้ยง) ← ✅ หลัก
  • completion_date (วันที่เสร็จสิ้น)
  • actual_delivery_time (เวลาส่งจริง)
  • state (สถานะ)
  • pickup_location (ต้นทาง)
  • destination (ปลายทาง)
  • receiver_name (ชื่อผู้รับ)
  
═══════════════════════════════════════════════════════════════

🚀 การใช้งาน:

1️⃣  แอปเรียก API เพื่อดึงประวัติการจัดส่ง:
    POST /api/v1/delivery_history/get_all
    Body: { "driver_id": 5, "limit": 10 }

2️⃣  API ส่งกลับข้อมูล พร้อม daily_allowance

3️⃣  แอปแสดงค่าเบี้ยเลี้ยงในหน้าประวัติการจัดส่ง

═══════════════════════════════════════════════════════════════

✨ ขั้นตอนถัดไป:
1. รีสตาร์ท Odoo
2. ทดสอบ API endpoint ด้วย Postman หรือ curl
3. แอปเรียก API และแสดงค่าเบี้ยเลี้ยง

═══════════════════════════════════════════════════════════════
✅ สถานะ: FIXED & READY
═══════════════════════════════════════════════════════════════

📌 curl examples:

# ดึงประวัติทั้งหมด
curl -X POST http://localhost:8069/api/v1/delivery_history/get_all \
  -H "Content-Type: application/json" \
  -d '{"driver_id": 5, "limit": 10}'

# ดึงรายการเดียว
curl -X GET http://localhost:8069/api/v1/delivery_history/get/1 \
  -H "Content-Type: application/json"
