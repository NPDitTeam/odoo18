# -*- coding: utf-8 -*-

from odoo import models

BILL_MOVE_TYPES = ['in_invoice', 'in_refund']


class AccountMove(models.Model):
    """เมนู บิลผู้ขาย"""

    _name = 'account.move'
    _inherit = ['account.move', 'npd.expense.review.mixin']

    def _npd_review_applicable(self):
        return self.filtered(lambda move: move.move_type in BILL_MOVE_TYPES)

    def _npd_review_write(self, vals):
        # สถานะตรวจสอบไม่กระทบตัวเลขบัญชี จึงให้กดได้แม้ใบอยู่ในงวดที่ล็อกแล้ว
        # (account_journal_lock_date เช็คล็อกทุกครั้งที่ write)
        return super(AccountMove, self.with_context(
            bypass_journal_lock_date=True))._npd_review_write(vals)
