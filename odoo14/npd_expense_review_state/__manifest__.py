# -*- coding: utf-8 -*-
{
    'name': 'NPD Expense Review State',
    'version': '18.0.1.0.0',
    'summary': 'สถานะ รอตรวจสอบ / ตรวจสอบแล้ว ของเอกสารรายจ่าย (บิลผู้ขาย / Avance Clear / การรับ)',
    'description': """
NPD Expense Review State (พอร์ตจาก Odoo 14)
==========================================
เพิ่มฟิลด์ "สถานะตรวจสอบ" แยกจากสถานะหลักของเอกสาร พร้อมปุ่ม
"ตรวจสอบแล้ว" และ "รอตรวจสอบ" ให้เอกสารรายจ่าย 3 เมนู
(ชุดเดียวกับที่โมดูล npd_head_office_branch อ้างอิง)

    * บิลผู้ขาย        (account.move ประเภท in_invoice / in_refund)
    * Avance Clear    (account.advance.clear)
    * การรับ           (account.voucher เฉพาะ check_type_show_selection = False)

ทุกใบเริ่มต้นเป็น "รอตรวจสอบ" (รวมเอกสารเก่าตอนติดตั้ง)
กดปุ่ม "ตรวจสอบแล้ว" จึงเปลี่ยนเป็น "ตรวจสอบแล้ว" พร้อมเก็บผู้ตรวจสอบและวันที่

สิทธิ์กดปุ่ม: กลุ่ม "Expense Review - แสดงปุ่มตรวจสอบแล้ว"
เปิดให้ผู้ใช้ได้ที่ ตั้งค่า > ผู้ใช้ > แท็บ Preferences > แสดงปุ่มตรวจสอบแล้ว
""",
    'category': 'Accounting',
    'author': 'NPD Dev',
    'license': 'AGPL-3',
    # o18 ไม่มีโมดูล account_voucher แยก ใบสำคัญอยู่ใน account_voucher_npd
    'depends': [
        'account',
        'mail',
        'account_voucher_npd',
        'account_advance',
    ],
    'data': [
        'security/security.xml',
        'views/account_move_views.xml',
        'views/account_advance_clear_views.xml',
        'views/account_voucher_views.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
