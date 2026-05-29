# -*- coding: utf-8 -*-
{
    'name': 'รายการตรวจสอบสภาพรถ',
    'version': '18.0.1.0.2',
    'category': 'Operations/Fleet',
    'summary': 'ระบบบันทึกการตรวจสอบสภาพรถประจำวัน',
    'description': """
        ระบบรายการตรวจสอบสภาพรถ
        - บันทึกการตรวจสอบสภาพรถ 24 รายการ
        - บันทึกข้อมูลการบำรุงรักษา (น้ำมันเครื่อง, กรองอากาศ, เกียร์, เฟืองท้าย)
        - บันทึกเลขไมล์และสถานะการครบกำหนดเปลี่ยนถ่าย
        - เชื่อมต่อกับแอปมือถือ NPD Logistics
        - รองรับการถ่ายภาพประกอบการตรวจสอบ
        - แสดงรูปภาพขนาดเล็กในรายการ กดเพื่อดูขนาดเต็ม
        - กำหนดสิทธิ์ผู้ใช้แยกตาม ยืนยัน/อนุมัติ/กลับเป็นร่าง
    """,
    'author': 'NPD Logistics',
    'website': 'https://www.npdhrms.com',
    'depends': [
        'base',
        'mail',
        'fleet',
        'vehicle_registration',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/vehicle_inspection_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'vehicle_inspection/static/src/css/vehicle_inspection.css',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
