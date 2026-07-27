# -*- coding: utf-8 -*-
{
    'name': 'NPD Invoice Billing Status',
    'summary': 'เพิ่มสถานะวางบิล ช่องทางวางบิล และแนบหลักฐานการวางบิล บนใบแจ้งหนี้',
    'description': """
สถานะวางบิลบนใบแจ้งหนี้ (พอร์ตจาก Odoo 14)
==========================================

เพิ่ม 3 ฟิลด์บน ``account.move``

* สถานะวางบิล (ยังไม่วางบิล / วางบิลแล้ว) — ค่าเริ่มต้น "ยังไม่วางบิล"
* วางบิลให้ลูกค้าผ่านช่องทาง (Email / Line / Facebook / ไปรษณีย์)
* แนบหลักฐานการวางบิล (ถ่ายภาพ, แคปหน้าจอ)

สองฟิลด์หลังจะแสดงและบังคับกรอกเมื่อเลือก "วางบิลแล้ว" เท่านั้น

ต่างจาก Odoo 14
---------------
* ของเดิม depends ``npd_print_select_account`` และแทรกฟิลด์ต่อจาก
  ``debt_payment_type`` — โมดูลนั้นยังไม่ได้พอร์ตมา Odoo 18 และฟิลด์
  ``debt_payment_type`` ก็ไม่ได้ถูกแสดงบนฟอร์มใบแจ้งหนี้ใน Odoo 18
  จึงย้ายมาแทรกต่อจากกลุ่มฟิลด์ NPD ที่ ``pfb_npd_all_customs`` เพิ่มไว้แทน
* เปลี่ยน ``attrs`` เป็น modifier แบบใหม่ของ Odoo 17+
    """,
    'version': '18.0.1.0.0',
    'author': 'NPD',
    'category': 'Accounting',
    'license': 'LGPL-3',
    # ยึดวิวกับโมดูลนี้แทน npd_print_select_account ที่ยังไม่ได้พอร์ตมา Odoo 18
    'depends': ['pfb_npd_all_customs'],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
}
