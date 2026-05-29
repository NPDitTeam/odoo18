# -*- coding: utf-8 -*-
{
    'name': 'Vehicle Booking API',
    'version': '18.0.1.0.0',
    'category': 'Transport',
    'summary': 'API สำหรับดึงข้อมูลจากตาราง vehicle.booking',
    'description': """
        API Endpoints สำหรับดึงข้อมูล Vehicle Booking:
        - ค่าเที่ยว (travel_expenses)
        - ค่าเบี้ยเลี้ยง (daily_allowance)
        - ชื่อคนขับ (driver_name)
        - วันเวลาออกเดินทางจริง (planned_start_date_t)
        - เดือน/ปี (แปลงจาก planned_start_date_t)
    """,
    'author': 'NPD',
    'depends': ['base', 'transport_booking'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
