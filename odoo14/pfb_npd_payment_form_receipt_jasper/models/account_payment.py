import logging
from decimal import Decimal, ROUND_HALF_UP

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# ชื่อบริษัทไทย/อังกฤษท้ายใบเสร็จ (o14 เลือกตามชื่อฐานข้อมูล, o18 ฐานเดียวจึงเลือกตามบริษัทที่ใช้งาน)
COMPANY_NAMES = [
    ('กรุงเทพ', 'บริษัท นภดล กรุงเทพ จํากัด', 'NOPPADOL BANGKOK CO.,LTD'),
    ('กรุ๊ป', 'บริษัท นภดล เอสกรุ๊ป จํากัด', 'NOPPADOL S GROUP CO.,LTD'),
    ('สตีลเทค', 'บริษัท เอ็นพีดี สตีลเทค จํากัด', 'NOPPADOL STEELTECH CO.,LTD'),
    ('โลจิสติกส์', 'บริษัท เอ็นพีดี โลจิสติกส์ จํากัด', 'NPD LOGISTICS CO.,LTD'),
    ('อินเตอร์เทรดดิ้ง', 'บริษัท นภดล อินเตอร์เทรดดิ้ง จํากัด', 'NOPPADOL INTERTRADING CO.,LTD'),
]


def _round_half_up(value):
    return float(Decimal(str(value or 0.0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # ฟิลด์สำหรับใบกำกับภาษี/ใบเสร็จรับเงิน (ค่าเช่า) — หัวกระดาษ/วิธีชำระ/ลายเซ็น ใช้ของ
    # npd_payment_receipt_jasper ร่วมกัน (jasper_*)
    jasper_pfr_untaxed = fields.Float(compute='_compute_jasper_pfr_amounts')
    jasper_pfr_vat = fields.Float(compute='_compute_jasper_pfr_amounts')
    jasper_pfr_wht = fields.Float(compute='_compute_jasper_pfr_amounts')
    jasper_pfr_net = fields.Float(compute='_compute_jasper_pfr_amounts')
    jasper_pfr_wht_show = fields.Char(compute='_compute_jasper_pfr_amounts')
    jasper_pfr_baht_text = fields.Char(compute='_compute_jasper_pfr_amounts')
    jasper_pfr_company_th = fields.Char(compute='_compute_jasper_pfr_company')
    jasper_pfr_company_en = fields.Char(compute='_compute_jasper_pfr_company')
    jasper_pfr_receipt_number = fields.Char(compute='_compute_jasper_pfr_receipt_number')

    # วันที่เริ่มใช้เลข Tax Invoice Number เป็น "เลขที่" ของใบกำกับภาษี-ใบเสร็จรับเงิน
    # (เหมือน o14 pfb_npd_payment_form_receipt) ใบก่อนวันนี้ยังเป็นเลขรับชำระ
    # ปรับได้ที่ ตั้งค่า > เทคนิค > System Parameters โดยไม่ต้องแก้โค้ด
    RECEIPT_TAX_NUMBER_PARAM = 'pfb_npd_payment_form_receipt.tax_number_from'
    RECEIPT_TAX_NUMBER_FROM = '2026-10-07'

    @api.depends('name', 'date', 'tax_invoice_ids.tax_invoice_number')
    def _compute_jasper_pfr_receipt_number(self):
        """ตั้งแต่วันที่กำหนด และมี Tax Invoice Number → ใช้เลขนั้น นอกนั้นใช้เลขรับชำระ"""
        start = self.env['ir.config_parameter'].sudo().get_param(
            self.RECEIPT_TAX_NUMBER_PARAM, self.RECEIPT_TAX_NUMBER_FROM)
        for rec in self:
            number = rec.name
            if rec.date and str(rec.date) >= start:
                numbers = rec.tax_invoice_ids.filtered(
                    lambda t: t.tax_invoice_number and not t.reversing_id and not t.reversed_id
                ).mapped('tax_invoice_number')
                if numbers:
                    number = ', '.join(dict.fromkeys(numbers))
            rec.jasper_pfr_receipt_number = number or ''

    def _pfr_wht_rent_5(self, untaxed_amount):
        """ภาษีหัก ณ ที่จ่าย 5% (ค่าเช่า) — ปัดฐานก่อน VAT เป็น 2 ตำแหน่งก่อนคิด 5% แบบ round-half-up
        เหมือน compute_wht_rent_5 ของ o14 (1,550.775 -> 1,550.78 ไม่ใช่ 1,550.77)"""
        base = Decimal(str(untaxed_amount or 0.0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return float((base * Decimal('5') / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    @api.depends('total_amount', 'amount', 'reconciled_invoice_ids', 'partner_id.company_type', 'wht_has_slip')
    def _compute_jasper_pfr_amounts(self):
        thb = self.env.ref('base.THB', raise_if_not_found=False)
        for rec in self:
            total = rec.total_amount or rec.amount or 0.0
            # แยก VAT ตามสัดส่วนใบแจ้งหนี้ที่ตัดชำระจริง (รองรับชำระไม่เต็มจำนวน) เหมือน o14
            inv_untaxed = sum(abs(i.amount_untaxed_signed) for i in rec.reconciled_invoice_ids)
            inv_total = sum(abs(i.amount_total_signed) for i in rec.reconciled_invoice_ids)
            if inv_total:
                vat = round(total * (inv_total - inv_untaxed) / inv_total, 2)
                untaxed = total - vat
            else:
                untaxed = total / 1.07
                vat = total - untaxed
            is_company = rec.partner_id.company_type == 'company'
            show_wht = is_company and not rec.wht_has_slip
            wht = rec._pfr_wht_rent_5(untaxed) if show_wht else 0.0
            net = total - wht
            rec.jasper_pfr_untaxed = untaxed
            rec.jasper_pfr_vat = vat
            rec.jasper_pfr_wht = wht
            rec.jasper_pfr_net = net
            rec.jasper_pfr_wht_show = 'X' if show_wht else ''
            currency = rec.currency_id or thb
            rec.jasper_pfr_baht_text = currency.with_context(lang='th_TH').amount_to_text(_round_half_up(net))

    @api.depends_context('company', 'allowed_company_ids')
    def _compute_jasper_pfr_company(self):
        name = self.env.company.name or ''
        th = name
        en = ''
        for token, thai_name, eng_name in COMPANY_NAMES:
            if token in name:
                th, en = thai_name, eng_name
                break
        for rec in self:
            rec.jasper_pfr_company_th = th
            rec.jasper_pfr_company_en = en
