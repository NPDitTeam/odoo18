# -*- coding: utf-8 -*-

from odoo import models


class AccountVoucher(models.Model):
    """เมนู การรับ - ใช้เฉพาะเอกสารที่ check_type_show_selection = False"""

    _name = 'account.voucher'
    _inherit = ['account.voucher', 'npd.expense.review.mixin']

    def _npd_review_applicable(self):
        return self.filtered(
            lambda voucher: voucher.check_type_show_selection != 'true')
