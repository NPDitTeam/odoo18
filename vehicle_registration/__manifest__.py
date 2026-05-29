# -*- coding: utf-8 -*-
{
    'name': 'ลงทะเบียนรถและการซ่อมบำรุง',
    'version': '18.0.1.1.0',
    'category': 'Operations/Inventory',
    'summary': 'ระบบลงทะเบียนรถ คนขับ และการซ่อมบำรุง',
    'description': """
        ระบบจัดการรถและการซ่อมบำรุง
        - ลงทะเบียนรถทั้งรถของบริษัทและรถร่วม
        - จัดการบริษัทรถร่วม
        - บันทึกข้อมูลผู้ขับขี่และใบอนุญาต
        - ระบบ PIN 6 หลักสำหรับผู้ขับขี่ (ไม่ซ้ำกัน)
        - จัดเก็บเอกสารรถ (ภาษี, พ.ร.บ., ประกันภัย)
        - ระบบแจ้งซ่อมและประวัติการซ่อมบำรุง
        - การแจ้งเตือนเอกสารหมดอายุและการบำรุงรักษา
        - ระบบการอนุมัติการแจ้งซ่อม
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'fleet',
        'mail',
        'transport_sync',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/vehicle_data.xml',
        'views/vehicle_views.xml',
        'views/maintenance_approval_views.xml',
        'views/maintenance_approval_wizard_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_backend': [
            'vehicle_registration/static/src/css/vehicle_image.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
