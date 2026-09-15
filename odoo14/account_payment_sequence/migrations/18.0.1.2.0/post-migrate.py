# -*- coding: utf-8 -*-
"""แยกเลขใบรับ/จ่ายชำระ ออกจากเลขรายการบันทึกบัญชี + รูปแบบเลขต่อบริษัทตาม Odoo 14

ดู models/payment_numbering.py
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['account.payment']._npd_setup_payment_numbering()
