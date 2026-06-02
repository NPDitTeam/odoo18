# -*- coding: utf-8 -*-
{
    'name': 'ขนส่ง',
    'version': '18.0.1.2.0',
    'category': 'Operations/Inventory',
    'summary': 'ระบบจัดการขนส่งและซิงค์ข้อมูลจาก Odoo 14',
    'description': """
        โมดูลสำหรับดึงข้อมูล Sale Order จาก Odoo 14
        - ดึงข้อมูลการขนส่ง
        - แปลง ID เป็นชื่อสำหรับ branch, partner, company
        - เก็บข้อมูลสินค้า
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'sale', 'stock', 'multi_branch_management_aagam'],
    'data': [
        # 'security/transport_security.xml',  # ✅ Comment ออกเพราะไม่ใช้ custom groups
        'security/ir.model.access.csv',
        'data/transport_sequence.xml',
        'data/transport_sync_cron.xml',
        'views/transport_order_views.xml',
        'views/transport_sync_menu.xml',
        'views/res_users_views.xml',  # ✅ เพิ่ม view สำหรับ User Preferences
        'views/sale_order_transport_views.xml',  # ปุ่มส่งไปยังระบบขนส่ง (odoo18)
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'sequence': 5,
}