# User Approver Module

## คำอธิบาย
โมดูลนี้เพิ่มฟิลด์ "ผู้อนุมัติ" ในโมดูล res.users เพื่อกำหนดว่าผู้ใช้คนใดเป็นผู้อนุมัติ

## Features
- ✅ เพิ่มฟิลด์ checkbox "ผู้อนุมัติ" ใน User Preferences
- ✅ ค่าเริ่มต้น: ไม่ติ๊ก (False)
- ✅ แสดงในหน้า List View ของผู้ใช้งาน (optional column)
- ✅ มี tracking เมื่อมีการเปลี่ยนแปลง
- ✅ บันทึก log เมื่อเปลี่ยนสถานะ

## การติดตั้ง
1. คัดลอกโฟลเดอร์ `user_approver` ไปยัง custom-addons
2. Restart Odoo service
3. เข้า Apps → Update Apps List
4. ค้นหา "User Approver"
5. คลิก Install

## การใช้งาน
1. ไปที่ Settings → Users & Companies → Users
2. เลือกผู้ใช้ที่ต้องการแก้ไข
3. ไปที่แท็บ "Preferences"
4. มองหาส่วน "สิทธิ์อนุมัติงานซ่อม"
5. ติ๊กที่ checkbox "ผู้อนุมัติ" ถ้าต้องการให้เป็นผู้อนุมัติ

## โครงสร้างโมดูล
```
user_approver/
├── __init__.py
├── __manifest__.py
├── README.md
├── models/
│   ├── __init__.py
│   └── res_users.py
├── views/
│   └── res_users_views.xml
└── security/
    └── ir.model.access.csv
```

## Version
- Odoo Version: 18.0
- Module Version: 1.0.0

## License
LGPL-3
