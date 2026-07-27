# -*- coding: utf-8 -*-
from odoo import Command, api, models

# ประเภทสมุดรายวันที่โมดูล account_journal_sequences เพิ่มเข้ามา
# และเราต้องการให้ใช้กับ account.payment ได้เหมือน Odoo 14
EXTRA_PAYMENT_JOURNAL_TYPES = ('receivable', 'payable')


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.depends('outbound_payment_method_line_ids', 'inbound_payment_method_line_ids')
    def _compute_available_payment_method_ids(self):
        """เปิดให้สมุดรายวัน รับชำระ/จ่ายชำระ ตั้งวิธีการชำระเงินได้

        Odoo 18 ตั้ง available_payment_method_ids = False ให้ทุกเล่มที่ไม่ใช่
        bank/cash/credit ทำให้สมุดรายวัน receivable/payable สร้าง
        account.payment.method.line ไม่ได้เลย และหน้ารับชำระใช้ไม่ได้

        Odoo 14 ไม่มีข้อจำกัดนี้ (โมดูล account_payment_sequence ตัวเดิม
        override domain ของ journal_id ให้เป็น receivable/payable ตรง ๆ)
        จึงเปิดให้เฉพาะวิธี 'manual' เหมือนที่ Odoo 14 ใช้อยู่
        """
        super()._compute_available_payment_method_ids()

        extra_journals = self.filtered(
            lambda j: j.type in EXTRA_PAYMENT_JOURNAL_TYPES)
        if not extra_journals:
            return

        manual_methods = self.env['account.payment.method'].search([
            ('code', '=', 'manual'),
        ])
        for journal in extra_journals:
            journal.available_payment_method_ids = [Command.set(manual_methods.ids)]
