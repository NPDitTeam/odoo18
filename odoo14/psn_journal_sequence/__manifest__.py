# -*- coding: utf-8 -*-
{
    'name': 'PSN Journal Sequence (Odoo 18)',
    'version': '18.0.1.0.0',
    'author': 'NPD',
    'category': 'Accounting',
    'license': 'LGPL-3',
    'summary': """
        คืนแท็บ Sequence บนสมุดรายวัน (ir.sequence) แบบ Odoo 14 ให้ใช้งานใน Odoo 18
    """,
    'description': """
Journal Sequence (พอร์ตจาก Odoo 14)
===================================

Odoo 18 เลิกใช้ ``ir.sequence`` ในการออกเลขที่ ``account.move`` แล้ว
เปลี่ยนไปใช้ ``sequence.mixin`` ที่เดาเลขถัดไปจาก "ชื่อเอกสารล่าสุด" ของสมุดรายวันแทน
ทำให้ไม่มีแท็บ Sequence บนฟอร์มสมุดรายวันเหมือน Odoo 14

โมดูลนี้นำพฤติกรรมแบบ Odoo 14 กลับมา:

* เพิ่มฟิลด์บน ``account.journal``
  ``sequence_id`` / ``sequence_number_next`` และ
  ``refund_sequence_id`` / ``refund_sequence_number_next``
* เพิ่มแท็บ **Sequence** บนฟอร์มสมุดรายวัน
* ถ้าสมุดรายวันเล่มไหน "ตั้ง sequence ไว้" เลขที่เอกสารของเล่มนั้นจะออกจาก
  ``ir.sequence`` ตอนโพสต์ (ไม่ใช้ตัวเดาเลขของ Odoo 18)
* สมุดรายวันที่ **ไม่ได้** ตั้ง sequence ยังทำงานตามมาตรฐาน Odoo 18 ทุกประการ

ส่วนที่ต้องปรับเพิ่มจาก Odoo 14 (เพราะ Odoo 18 มีกลไกใหม่)
----------------------------------------------------------
* ปิด constraint ``_constrains_date_sequence`` เฉพาะเอกสารที่ใช้ sequence เอง
  ไม่งั้นเลขที่ที่ไม่ตรงรูปแบบวันที่ (เช่น พ.ศ. หรือ prefix เฉพาะ) จะโดน ValidationError
* ปิดธง ``made_sequence_gap`` (เลขที่แดงใน list + ฟิลเตอร์ Irregular Sequences)
  เพราะ ``ir.sequence`` แบบ standard ข้ามเลขได้ตามปกติเมื่อ transaction rollback
* ไม่แสดง ``name_placeholder`` ที่ Odoo 18 เดาให้ เพราะเลขจริงมาจาก ir.sequence
* กัน "ออกเลขซ้ำทับของเดิม": เอกสารที่มีเลขที่อยู่แล้วจะไม่ถูกออกเลขใหม่
  (Odoo 14 รุ่นเดิมไม่มีการกันตรงนี้)
* ``next_by_id`` ส่ง ``sequence_date=move.date`` ให้ ir.sequence เพื่อให้
  sub-sequence ราย เดือน/ปี อิงวันที่ลงบัญชี ไม่ใช่วันที่กดโพสต์
  (ทำงานร่วมกับโมดูล ``npd_generate_subsequences``)
    """,
    'depends': [
        'account',
    ],
    'data': [
        'views/account_journal_view.xml',
        'views/account_move_view.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
