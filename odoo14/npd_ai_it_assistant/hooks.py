# -*- coding: utf-8 -*-
u"""งานตั้งค่าที่ทำด้วยไฟล์ data ไม่ได้

เปิดสิทธิ์ "ยกเลิก" ให้ผู้ใช้ระบบ (__system__ / OdooBot)
------------------------------------------------------
หัวข้อ "แก้ไขวันที่ใบแจ้งหนี้" ต้องยกเลิกใบที่ลงบันทึกแล้ว ซึ่งชนด่านสิทธิ์
ที่กระจายอยู่หลายโมดูล แต่ละด่านเช็คธงบน res.users คนละตัว (ดู SYSTEM_CANCEL_FLAGS)

ข้อควรรู้: ตั้งแต่ Odoo 13 เป็นต้นมา ``sudo()`` "ไม่เปลี่ยน env.user" แล้ว
(ดู models.py: "The superuser mode does not change the current user") มันแค่
ข้าม access rights/record rules เท่านั้น ด่านที่เช็คจากตัวผู้ใช้จึงยังเจอ
พนักงานคนเดิมอยู่ โค้ดฝั่งเราจึงใช้ ``with_user(SUPERUSER_ID)`` เพื่อให้
env.user กลายเป็น __system__ จริง ๆ แล้วอาศัยการติ๊ก allow_cancel ที่นี่

ทำเป็น hook แทนไฟล์ data เพราะไม่อยากประกาศ user_cancel_control เป็น depends
(ฐานข้อมูลที่ยังไม่ได้ติดตั้งโมดูลนั้น จะโดนบังคับติดตั้งด่านเพิ่มโดยไม่ตั้งใจ)
ที่นี่จึงเช็คก่อนว่ามีฟิลด์จริงไหม ถ้าไม่มีก็ข้ามไปเงียบ ๆ

ขอบเขตผลกระทบ: ปลดล็อกเฉพาะโค้ดที่รันในนามผู้ใช้ระบบ พนักงานที่กดปุ่มบนหน้าจอ
ยังถูกด่าน allow_cancel เดิมคุมอยู่ครบ ด่านของเมนูนี้คือ เช็คสาขาของพนักงาน +
บังคับพิมพ์ "ยืนยัน" + เขียน log ลง session / chatter ของเอกสาร / log เซิร์ฟเวอร์
ถ้าต้องการยกเลิกการปลดล็อก ให้ติ๊ก allow_cancel ของผู้ใช้ __system__ ออก
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# ธงสิทธิ์บน res.users ที่ด่านต่าง ๆ ในระบบใช้กันการยกเลิก/รีเซ็ตเป็นร่าง
# ต้องเปิดให้ผู้ใช้ระบบครบทุกตัว ไม่งั้นการยกเลิกจะไปตายกลางทางทีละด่าน
#   allow_cancel                     user_cancel_control      -> account.move.button_draft()
#   account_payment_lock_draft_date  account_payment_invoice  -> account.payment.action_draft()
# โมดูลไหนไม่ได้ติดตั้ง ฟิลด์ก็จะไม่มี โค้ดจะข้ามให้เอง
SYSTEM_CANCEL_FLAGS = (
    'allow_cancel',
    'account_payment_lock_draft_date',
)


def grant_system_cancel_right(env):
    """ติ๊กธงสิทธิ์ยกเลิกให้ผู้ใช้ระบบ (idempotent)"""
    env = api.Environment(env.cr, SUPERUSER_ID, {})
    root = env.ref('base.user_root', raise_if_not_found=False)
    if not root:
        return

    fields_available = env['res.users']._fields
    values = {}
    for flag in SYSTEM_CANCEL_FLAGS:
        if flag not in fields_available:
            _logger.info('ตัวช่วย AI-IT: ฐานข้อมูลนี้ไม่มีฟิลด์ %s ข้ามการตั้งค่า', flag)
            continue
        if not root[flag]:
            values[flag] = True

    if values:
        root.sudo().write(values)
        _logger.info('ตัวช่วย AI-IT: เปิดสิทธิ์ %s ให้ผู้ใช้ระบบ (__system__) แล้ว',
                     ', '.join(values))


def post_init_hook(env):
    grant_system_cancel_right(env)
