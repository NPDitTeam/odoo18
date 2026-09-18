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


# ผู้ใช้ที่ได้รับอนุญาตให้เห็นหัวข้อ "ช่วยปิดงบ" ตั้งแต่ต้น (ตามที่ผู้ใช้ระบุ)
# เทียบด้วย login แบบไม่สนตัวพิมพ์ใหญ่-เล็ก และ "ข้ามคนที่ไม่มีในฐานนั้น" ให้เอง
# หลังจากนี้ผู้ดูแลเพิ่ม/ถอนสิทธิ์เองได้ที่หน้าผู้ใช้
CLOSING_HELP_LOGINS = (
    'Mayurada_center',
    'Articha_center',
    'sattaya_center',
    'Patchareeda',
    'User04',
    'User004',
    'Npd_admin',
)


def grant_closing_help_users(env):
    """ติ๊กสิทธิ์ "ใช้หัวข้อช่วยปิดงบ" ให้ผู้ใช้ชุดตั้งต้น (idempotent)

    ไม่ถอนสิทธิ์ของใครออก — ถ้าผู้ดูแลติ๊กเพิ่มให้คนอื่นไว้ การอัปเดตโมดูล
    รอบถัดไปต้องไม่ไปลบทิ้ง
    """
    group = env.ref('npd_ai_it_assistant.group_ai_it_closing', raise_if_not_found=False)
    if not group:
        return

    Users = env['res.users'].sudo().with_context(active_test=False)
    users = Users.search([('login', 'in', list(CLOSING_HELP_LOGINS))])
    found_logins = {user.login.lower() for user in users}
    # login ในฐานจริงอาจพิมพ์ต่างตัวใหญ่-เล็ก จึงค้นซ้ำแบบ ilike เฉพาะที่ยังไม่เจอ
    for login in CLOSING_HELP_LOGINS:
        if login.lower() in found_logins:
            continue
        extra = Users.search([('login', '=ilike', login)], limit=1)
        if extra:
            users |= extra
            found_logins.add(extra.login.lower())

    missing = [login for login in CLOSING_HELP_LOGINS
               if login.lower() not in found_logins]
    if missing:
        _logger.info('ตัวช่วย AI-IT: ฐานนี้ไม่มีผู้ใช้ %s จึงข้ามการให้สิทธิ์ปิดงบ',
                     ', '.join(missing))

    to_add = users - group.users
    if to_add:
        group.sudo().write({'users': [(4, user.id) for user in to_add]})
        _logger.info('ตัวช่วย AI-IT: ให้สิทธิ์หัวข้อช่วยปิดงบแก่ %s',
                     ', '.join(to_add.mapped('login')))


def post_init_hook(env):
    grant_system_cancel_right(env)
    grant_closing_help_users(env)
