# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    npd_tax_invoice_number = fields.Char(
        string='เลขใบกำกับภาษีที่ออกให้', copy=False, readonly=True,
        help='เลขจากสมุดรายวันรับชำระ (แท็บ "เลขใบกำกับภาษี") '
             'กลับเป็นร่างแล้วยืนยันใหม่ใช้เลขเดิม ไม่ออกเลขใหม่',
    )
