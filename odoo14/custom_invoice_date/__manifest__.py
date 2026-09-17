# -*- coding: utf-8 -*-
{
    'name': 'Custom Invoice Date Management',
    'version': '18.0.1.1.0',
    'category': 'Accounting',
    'summary': 'จัดการวันที่ Invoice และใบเสนอราคาแบบจอง',
    'description': """
        พอร์ตจาก Odoo 14 (custom_invoice_date 14.0.1.1.0)
        - ใบเสนอราคาแบบจอง (ติ๊กบนใบสั่งขาย) -> ใบแจ้งหนี้ต้องให้ส่วนกลางระบุวันที่ก่อนยืนยัน
        - แก้ไขวันที่ Invoice ได้เฉพาะผู้ใช้ที่ได้รับอนุญาต (สำหรับเอกสารที่มาจากใบสั่ง)
        - ช่องติ๊กภาษีหัก ณ ที่จ่าย 5% ของใบแจ้งหนี้/ใบวางบิล
    """,
    'author': 'Your Company',
    'depends': [
        'base',
        'account',
        'sale',
    ],
    'data': [
        'views/res_users_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
