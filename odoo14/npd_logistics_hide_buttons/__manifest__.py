# -*- coding: utf-8 -*-
{
    'name': 'NPD Logistics ซ่อนปุ่มใบสั่งขาย',
    'version': '18.0.1.0.0',
    'summary': 'บริษัท เอ็นพีดี โลจิสติกส์ ไม่ใช้ปุ่ม "ยกเลิกรายการอ้างอิงบิลเช่า" และ "ตัดสต๊อก Auto" — ซ่อนในใบสั่งขาย',
    'category': 'Sales',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['transport_sync', 'so_auto_stock_cut', 'sale_order_cancel_wizard'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
