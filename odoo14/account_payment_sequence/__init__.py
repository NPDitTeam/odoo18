from . import models


def post_init_hook(env):
    """ตั้งรูปแบบเลขใบรับ/จ่ายชำระและสมุดรายวันรับ/จ่ายชำระตาม Odoo 14 ให้ทุกบริษัท

    เดิมบังคับ prefix ของ sequence กลางตัวเดียวให้ทุกบริษัท (เลขปนกันข้ามบริษัท)
    ดูรายละเอียดที่ models/payment_numbering.py
    """
    env['account.payment']._npd_setup_payment_numbering()
