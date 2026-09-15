# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    wht_has_slip = fields.Boolean(
        string="ยังไม่ได้รับใบหัก ณ ที่จ่าย",
        default=False,  # ค่าเริ่มต้นไม่ต้องติ๊ก
        help="ติ๊กเมื่อการชำระเงินนี้มีใบหัก ณ ที่จ่ายแนบประกอบ"
    )

    received_payment = fields.Boolean(
        string="ได้รับใบหัก ณ ที่จ่าย",
        default=False,
    )

    # o14 โมดูลนี้ประกาศ pfb_date_of_rent (Float) ไว้ด้วย แต่ o18 account_payment_invoice
    # ประกาศฟิลด์ชื่อนี้เป็นวันที่แล้ว ประกาศซ้ำคนละชนิดจะทับกัน จึงไม่ใส่ที่นี่
