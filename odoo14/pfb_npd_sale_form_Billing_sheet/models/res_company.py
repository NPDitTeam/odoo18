# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    promptpay_id = fields.Char(
        string="พร้อมเพย์ (PromptPay ID)",
        help="เลขพร้อมเพย์ของบริษัท ใช้สร้าง QR สแกนจ่ายบนใบแจ้งหนี้/ใบวางบิล\n"
             "- เบอร์มือถือ 10 หลัก เช่น 0812345678\n"
             "- เลขประจำตัวผู้เสียภาษี/บัตรประชาชน 13 หลัก\n"
             "- e-Wallet ID 15 หลัก\n"
             "ถ้าเว้นว่าง เอกสารจะแสดงรูป QR เดิมของบริษัทแทน")
