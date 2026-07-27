# -*- coding: utf-8 -*-
"""ล้าง layout ที่ ks_list_view_manager จำไว้ ของโมเดลตั้งค่าสมุดรายวัน

โมดูล ks_list_view_manager บันทึกลำดับ+รายชื่อคอลัมน์ของ list view ไว้รายผู้ใช้
(ตาราง user_specific / user_fields) แล้วใช้ค่านั้นแทน arch ตอน get_views

พอเราเพิ่มฟิลด์ใหม่เข้า list view ค่าที่จำไว้จะยังเป็นชุดฟิลด์เก่า ทำให้
  - ฟิลด์ใหม่ไปโผล่หน้าสุด (ลำดับเพี้ยน) หรือ
  - เปิดเมนูไม่ได้เลย ขึ้น "field is undefined" เพราะ arch มีฟิลด์ที่ layout ไม่รู้จัก

ลบทิ้งแล้วโมดูลจะสร้างใหม่จาก arch ปัจจุบันเองตอนเปิดเมนูครั้งถัดไป
"""
import logging

_logger = logging.getLogger(__name__)

MODELS = ['npd.invoice.journal.config']


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.tables WHERE table_name = 'user_specific'
    """)
    if not cr.fetchone():
        return  # ไม่ได้ติดตั้ง ks_list_view_manager

    cr.execute("""
        DELETE FROM user_fields
         WHERE fields_list IN (SELECT id FROM user_specific WHERE model_name = ANY(%s))
    """, (MODELS,))
    removed_fields = cr.rowcount

    cr.execute("DELETE FROM user_specific WHERE model_name = ANY(%s)", (MODELS,))
    _logger.info(
        "ล้าง layout ของ ks_list_view_manager: %s layout, %s field",
        cr.rowcount, removed_fields,
    )
