import logging
from decimal import Decimal, ROUND_HALF_UP

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def _money(value):
    return float(Decimal(str(value or 0.0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # ใบเสร็จค่าประกัน / ค่าปรับชำรุด / ค่าปรับหาย — หัวกระดาษ/วิธีชำระเงิน/ลายเซ็น
    # ใช้ฟิลด์ร่วมกับใบเสร็จรับเงินค่าขนส่ง (npd_payment_receipt_jasper)
    jasper_prc_origin = fields.Char(compute='_compute_jasper_prc_values')
    jasper_prc_baht_text = fields.Char(compute='_compute_jasper_prc_values')
    jasper_prc_collector = fields.Char(compute='_compute_jasper_prc_values')
    # ยอดสำหรับใบค่าปรับหาย (คิดจากใบแจ้งหนี้ที่ถูกตัดชำระ)
    jasper_prc_gross = fields.Float(compute='_compute_jasper_prc_values')
    jasper_prc_discount = fields.Float(compute='_compute_jasper_prc_values')
    jasper_prc_after_discount = fields.Float(compute='_compute_jasper_prc_values')
    jasper_prc_vat = fields.Float(compute='_compute_jasper_prc_values')
    jasper_prc_untaxed = fields.Float(compute='_compute_jasper_prc_values')
    jasper_prc_total = fields.Float(compute='_compute_jasper_prc_values')
    jasper_prc_line_ids = fields.Many2many('account.move.line', compute='_compute_jasper_prc_values')

    def _prc_invoices(self):
        """ใบแจ้งหนี้ที่ใบรับชำระนี้ตัดชำระ (o14 ใช้ invoice_ids ของตารางการชำระเงิน / reconciled_invoice_ids)"""
        self.ensure_one()
        invoices = self.env['account.move']
        if 'custom_invoice_ids' in self._fields:
            invoices |= self.custom_invoice_ids.mapped('move_id')
        return invoices or self.reconciled_invoice_ids

    @api.depends('total_amount', 'amount', 'custom_invoice_ids', 'reconciled_invoice_ids', 'create_uid')
    def _compute_jasper_prc_values(self):
        thb = self.env.ref('base.THB', raise_if_not_found=False)
        for rec in self:
            invoices = rec._prc_invoices()
            origins = [m.invoice_origin for m in invoices if m.invoice_origin]
            rec.jasper_prc_origin = origins[0] if origins else ''
            rec.jasper_prc_collector = rec.create_uid.name or ''
            total_amount = rec.total_amount or rec.amount or 0.0
            currency = rec.currency_id or thb
            rec.jasper_prc_baht_text = currency.with_context(lang='th_TH').amount_to_text(_money(total_amount))

            lines = invoices.mapped('invoice_line_ids').filtered(lambda l: l.display_type == 'product')
            rec.jasper_prc_line_ids = lines
            # o14 ใช้ amount_price_total_full = ยอดเต็มก่อนหักส่วนลด (= Σ price_unit × qty ของบรรทัด)
            gross = sum((l.price_unit or 0.0) * (l.quantity or 0.0) for l in lines)
            untaxed = sum(invoices.mapped('amount_untaxed'))
            vat = sum(invoices.mapped('amount_tax'))
            if invoices and 'amount_price_total_full' in invoices._fields:
                gross = sum(invoices.mapped('amount_price_total_full')) or gross
            rec.jasper_prc_gross = gross
            # o14 อ่านส่วนลดจาก discount_amount_computed (โมดูล bi_sale_purchase_discount_with_tax)
            # o18 ยังไม่ได้ติดตั้งโมดูลนั้น -> ใช้ผลต่างจากยอดก่อนภาษีแทน
            if invoices and 'discount_amount_computed' in invoices._fields:
                rec.jasper_prc_discount = sum(invoices.mapped('discount_amount_computed'))
            else:
                rec.jasper_prc_discount = max(gross - untaxed, 0.0)
            # o14 แถว "ค่าสินค้าหลังหักส่วนลด" = amount_untaxed + ภาษีมูลค่าเพิ่ม
            rec.jasper_prc_after_discount = untaxed + vat
            rec.jasper_prc_vat = vat
            rec.jasper_prc_untaxed = untaxed
            rec.jasper_prc_total = sum(invoices.mapped('amount_total'))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # ใบค่าปรับหาย: ไล่รายการสินค้าจากใบแจ้งหนี้ (o14 ตัด "(R)" ออกจากชื่อสินค้า)
    jasper_prc_product = fields.Char(compute='_compute_jasper_prc_line')
    jasper_prc_code = fields.Char(compute='_compute_jasper_prc_line')
    jasper_prc_price = fields.Char(compute='_compute_jasper_prc_line')
    jasper_prc_qty = fields.Char(compute='_compute_jasper_prc_line')
    jasper_prc_amount = fields.Char(compute='_compute_jasper_prc_line')

    def _compute_jasper_prc_line(self):
        for line in self:
            product = line.product_id
            name = (product.name or line.name or '').replace('(R)', '').strip()
            line.jasper_prc_product = name
            line.jasper_prc_code = product.default_code or ''
            line.jasper_prc_price = '{:,.2f}'.format(line.price_unit or 0.0)
            line.jasper_prc_qty = '{:,.0f}'.format(line.quantity or 0.0)
            line.jasper_prc_amount = '{:,.2f}'.format((line.price_unit or 0.0) * (line.quantity or 0.0))
