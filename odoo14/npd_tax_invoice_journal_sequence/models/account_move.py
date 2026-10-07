# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_tax_invoice_number(self, move, tax_invoice, tax):
        """ภาษีขายของใบรับชำระ (ไม่มี Tax Invoice Sequence ที่ตัวภาษี)
        ถ้าสมุดรายวันรับชำระตั้ง "ใช้เลขใบกำกับภาษีของตัวเอง" → ใช้เลขรันของเล่มนั้น
        ใบรับชำระหนึ่งใบได้เลขเดียว (ชำระหลายใบแจ้งหนี้ก็เลขเดียวกัน = ใบกำกับภาษี/ใบเสร็จหนึ่งฉบับ)
        และจำไว้ที่ใบรับชำระ รีเซ็ตแล้วยืนยันใหม่ได้เลขเดิม
        ไม่ได้ตั้ง → ค่าเดิมของ l10n_th_account_tax"""
        was_empty = not tax_invoice.tax_invoice_number
        number, invoice_date = super()._get_tax_invoice_number(move, tax_invoice, tax)
        if not (was_empty and tax and not tax.taxinv_sequence_id
                and tax.type_tax_use == 'sale' and move.move_type == 'entry'):
            return number, invoice_date
        if move.reversed_entry_id:
            # รายการกลับภาษี (รีเซ็ตใบรับชำระ) ต้องอ้างเลขใบกำกับภาษีเดิม รายงานภาษีจะหักล้างกันได้
            # ไม่ใช่ชื่อรายการบัญชีของใบ CABA ต้นทาง
            origin = move.reversed_entry_id.tax_invoice_ids.filtered(
                lambda t: t.tax_line_id == tax and t.tax_invoice_number)[:1]
            return (origin.tax_invoice_number or number), invoice_date
        # ใบ CABA ตอน post อาจยังไม่ผูก payment_id → ใช้ context ที่ _create_tax_cash_basis_moves ส่งมา
        payment = (tax_invoice.payment_id or move.origin_payment_id
                   or self.env['account.payment'].browse(self.env.context.get('payment_id') or []))
        if len(payment) != 1:
            return number, invoice_date
        if payment.npd_tax_invoice_number:
            return payment.npd_tax_invoice_number, invoice_date
        own = payment.journal_id._npd_next_taxinv_number(sequence_date=payment.date or move.date)
        if own:
            payment.sudo().npd_tax_invoice_number = own
            number = own
        return number, invoice_date
