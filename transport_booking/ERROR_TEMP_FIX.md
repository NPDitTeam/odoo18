# ❌ Error: ไม่มีฟิลด์ "rating_date" ใน vehicle.booking

## ปัญหา
Odoo บ่นว่า "ไม่มีฟิลด์ 'rating_date' ในโมเดล 'vehicle.booking'" แม้ว่า field นี้อยู่ใน tree view ของ `rating_ids` ซึ่งเป็น One2many ของ `delivery.rating`

## การแก้ไขชั่วคราว
ลบ field `rating_date` ออกจาก tree view ชั่วคราวเพื่อให้ module load ได้ก่อน

## ไฟล์ที่แก้ไข
1. `models/delivery_rating.py`:
   - ลบ `tracking=True` ออกจาก field `state`
   
2. `views/vehicle_booking_views.xml`:
   - ลบบรรทัด `<field name="rating_date" string="วันที่ประเมิน"/>` ออกจาก tree view ชั่วคราว

## การทดสอบ
```bash
cd C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking
restart_odoo_rating_fix.bat
```

หาก module load สำเร็จ แสดงว่าปัญหาเกิดจาก field `rating_date` ใน tree view

## Next Steps
ถ้า load สำเร็จ:
1. Upgrade module
2. ทดสอบการทำงาน
3. หาวิธีเพิ่ม field `rating_date` กลับมาโดยไม่เกิด error

ถ้ายัง error:
1. ตรวจสอบ error message ใหม่
2. แก้ไขตาม error ที่เกิดขึ้น
