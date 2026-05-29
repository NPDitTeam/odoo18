# -*- coding: utf-8 -*-
{
    'name': 'User Approver',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'เพิ่มฟิลด์ผู้อนุมัติในผู้ใช้งาน',
    'description': """
        เพิ่มฟิลด์ผู้อนุมัติในโมดูล res.users
        - ติ๊กเพื่อกำหนดว่าผู้ใช้คนนี้เป็นผู้อนุมัติหรือไม่
        - ค่าเริ่มต้นไม่ติ๊ก
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
