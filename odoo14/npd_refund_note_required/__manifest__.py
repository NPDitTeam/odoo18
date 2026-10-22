# -*- coding: utf-8 -*-
{
    'name': 'NPD ใบลดหนี้ บังคับกรอกเงื่อนไขและข้อกำหนด',
    'version': '18.0.1.1.0',
    'summary': 'ใบลดหนี้ลูกค้าต้องกรอกช่อง เงื่อนไขและข้อกำหนด (narration) ก่อนบันทึก/ยืนยัน',
    'description': """
* ฟอร์มใบลดหนี้ลูกค้า (out_refund) ที่ยังเป็นร่าง: ช่องเงื่อนไขและข้อกำหนดเป็นช่องบังคับ
* กดยืนยันแล้วช่องว่าง = แจ้งเตือน ไม่ให้ยืนยัน (เฉพาะเอกสารที่ไม่เคยยืนยันมาก่อน)
* ช่องเงื่อนไขและข้อกำหนดบนฟอร์มเป็นข้อความธรรมดา (ไม่ใช่ตัวแก้ HTML) — เก็บลง narration เดิม
* พอร์ตจาก o14 npd_refund_note_required
    """,
    'category': 'Accounting',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
