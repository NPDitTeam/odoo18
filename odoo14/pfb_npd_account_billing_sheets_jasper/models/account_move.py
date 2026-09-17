import base64
import logging
import re
from decimal import Decimal, ROUND_HALF_UP

from odoo import api, fields, models
from odoo.addons.pfb_npd_sale_form_Billing_sheet_jasper.models.sale_order import PAYMENT_INFO, _fmt_date

_logger = logging.getLogger(__name__)


def _round_half_up(value):
    return float(Decimal(str(value or 0.0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------
    # ฟิลด์สำหรับ Jasper (ไม่เก็บลงฐาน) — ขึ้นต้น jasper_abs_ กันชนกับรายงานตัวอื่นบน account.move
    # o14 (pfb_npd_account_billing_sheets): หัวกระดาษ/บัญชีรับเงินแยกตาม DB ของบริษัท
    # o18 ฐานเดียวหลายบริษัท -> ใช้บริษัทของใบแจ้งหนี้ (company_id)
    # ------------------------------------------------------------------
    jasper_abs_company_id = fields.Many2one('res.company', compute='_compute_jasper_abs_values')
    jasper_abs_company_name = fields.Char(compute='_compute_jasper_abs_values')
    jasper_abs_company_address = fields.Char(compute='_compute_jasper_abs_values')
    jasper_abs_company_vat_line = fields.Char(compute='_compute_jasper_abs_values')
    jasper_abs_partner_address = fields.Char(compute='_compute_jasper_abs_values')
    jasper_abs_invoice_date = fields.Char(compute='_compute_jasper_abs_values')
    jasper_abs_due_date = fields.Char(compute='_compute_jasper_abs_values')
    jasper_abs_note = fields.Char(compute='_compute_jasper_abs_values')
    jasper_abs_baht_text = fields.Char(compute='_compute_jasper_abs_values')

    # ใบค่าเช่าส่วนต่าง (บรรทัดสรุปเดียว)
    jasper_abs_diff_line = fields.Char(compute='_compute_jasper_abs_values')
    jasper_abs_days = fields.Integer(compute='_compute_jasper_abs_values')
    jasper_abs_rent_per_day = fields.Float(compute='_compute_jasper_abs_values')
    jasper_abs_wht_line = fields.Char(compute='_compute_jasper_abs_values')

    # ใบค่าปรับหาย/ชำรุด (ไล่รายการสินค้า ไม่รวมบรรทัดหัวข้อ/หมายเหตุ)
    jasper_abs_line_ids = fields.Many2many('account.move.line', compute='_compute_jasper_abs_values')

    jasper_abs_payment_text = fields.Char(compute='_compute_jasper_abs_payment')
    jasper_abs_qr_title = fields.Char(compute='_compute_jasper_abs_payment')
    jasper_abs_qr_image = fields.Binary(compute='_compute_jasper_abs_payment', attachment=False)

    def _abs_payment_info(self):
        self.ensure_one()
        name = self.company_id.name or ''
        for info in PAYMENT_INFO:
            if info['token'] in name:
                return info
        return {}

    def _abs_days(self):
        """o14 get_billing_sheet_days: หัวเอกสารมักเป็น 0 เพราะกรอกจำนวนวันที่บรรทัด
           จึงใช้ค่ามากสุดของบรรทัดก่อน แล้วค่อยใช้หัวเอกสาร"""
        self.ensure_one()
        days = max(self.invoice_line_ids.mapped('pfb_date_of_rent') or [0])
        return days or self.pfb_date_of_rent or 0

    def _compute_jasper_abs_values(self):
        SaleOrder = self.env['sale.order']
        for move in self:
            company = move.company_id
            info = move._abs_payment_info()
            move.jasper_abs_company_id = company
            move.jasper_abs_company_name = company.name or ''
            move.jasper_abs_company_address = SaleOrder._bs_join_address([
                company.street, company.street2, company.city,
                company.state_id.name if company.state_id else '', company.zip])
            head_office = '' if company.parent_id else ' (สำนักงานใหญ่)'
            # o14 ฐาน NPD_S_Group_New_V2 ไม่แสดงเลขประจำตัวผู้เสียภาษี (แสดงแค่สำนักงานใหญ่)
            move.jasper_abs_company_vat_line = head_office.strip() if info.get('hide_vat') else \
                'เลขประจำตัวผู้เสียภาษี %s%s' % (company.vat or '', head_office)

            partner = move.partner_id
            move.jasper_abs_partner_address = SaleOrder._bs_join_address([
                partner.street, partner.street2, partner.city,
                partner.state_id.name if partner.state_id else '', partner.zip])
            move.jasper_abs_invoice_date = _fmt_date(move.invoice_date)
            move.jasper_abs_due_date = _fmt_date(move.invoice_date_due)
            note = re.sub(r'</p>\s*<p>', ' ', str(move.narration or ''))
            move.jasper_abs_note = re.sub(r'<[^>]*>', '', note).strip()
            currency = move.currency_id or self.env.ref('base.THB')
            move.jasper_abs_baht_text = currency.with_context(lang='th_TH').amount_to_text(move.amount_total)

            days = move._abs_days()
            move.jasper_abs_days = days
            # o14 หารด้วย pfb_date_of_rent ของหัวเอกสาร (มักเป็น 0) ทำให้ค่าเช่าต่อวันไม่ตรงกับช่องจำนวนวัน
            # ใช้จำนวนวันชุดเดียวกับที่แสดง
            move.jasper_abs_rent_per_day = move.amount_total / days if days else move.amount_total
            move.jasper_abs_diff_line = 'ค่าเช่าส่วนต่าง เอกสารเลขที่ :%s' % (move.invoice_origin or move.name or '')
            if partner.company_type == 'company':
                base = _round_half_up(move.amount_untaxed)
                wht = _round_half_up(Decimal(str(move.amount_untaxed or 0.0)) * Decimal('0.05'))
                move.jasper_abs_wht_line = 'ภาษีหัก ณ ที่จ่าย 5%% ของ :     %s     =     %s     บาท' % (
                    '{:,.2f}'.format(base), '{:,.2f}'.format(wht))
            else:
                move.jasper_abs_wht_line = ''
            move.jasper_abs_line_ids = move.invoice_line_ids.filtered(lambda l: l.display_type == 'product')

    # ------------------------------------------------------------------
    # การชำระเงิน + QR พร้อมเพย์ระบุยอด = จำนวนเงินทั้งสิ้น (เหมือนใบแจ้งหนี้/ใบวางบิล Jasper)
    # ------------------------------------------------------------------
    def _abs_promptpay_payload(self):
        self.ensure_one()
        SaleOrder = self.env['sale.order']
        digits = re.sub(r'\D', '', self.company_id.promptpay_id or '')
        if len(digits) == 15:
            tag, account = '03', digits
        elif len(digits) == 13:
            tag, account = '02', digits
        elif len(digits) in (9, 10):
            tag, account = '01', '0066' + digits[-9:]
        else:
            return ''
        tlv = SaleOrder._promptpay_tlv
        merchant = tlv('00', 'A000000677010111') + tlv(tag, account)
        payload = tlv('00', '01') + tlv('01', '12') + tlv('29', merchant) + tlv('53', '764')
        payload += tlv('54', '%.2f' % _round_half_up(self.amount_total)) + tlv('58', 'TH') + '6304'
        return payload + SaleOrder._promptpay_crc16(payload)

    def _compute_jasper_abs_payment(self):
        SaleOrder = self.env['sale.order']
        for move in self:
            info = move._abs_payment_info()
            lines = []
            if info:
                lines.append('โอนเงินเข้าบัญชี : %s' % info['account'])
                lines.append('สั่งจ่ายด้วยเช็คกรุณาสั่งจ่ายในนาม : %s' % info['payee'])
            lines.append('ค่าธรรมเนียมธนาคาร ผู้ชำระเงินเป็นผู้รับผิดชอบ')
            move.jasper_abs_payment_text = '\n'.join(lines)
            image = False
            title = ''
            payload = move._abs_promptpay_payload()
            if payload:
                try:
                    png = self.env['ir.actions.report'].barcode('QR', payload, width=220, height=220)
                    image = base64.b64encode(png)
                    title = 'สแกนจ่ายด้วยพร้อมเพย์'
                except Exception as e:  # noqa: BLE001
                    _logger.warning("promptpay QR error on %s: %s", move.name, e)
            if not image:
                image = SaleOrder._bs_fallback_qr(info)
            move.jasper_abs_qr_image = image
            move.jasper_abs_qr_title = title


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def npd_abs_hide_retired_reports(self):
        """ซ่อนใบแจ้งหนี้ค่าเช่าส่วนต่างแบบเก่าจากเมนูพิมพ์ (ถ้ามีโมดูลนั้นอยู่) — ไม่ลบรายงาน
           เรียกคืนได้โดยอัปเกรดโมดูล pfb_npd_rental_difference_jasper"""
        old = self.env.ref('pfb_npd_rental_difference_jasper.jasper_rental_difference_report',
                           raise_if_not_found=False)
        if old and old.binding_model_id:
            old.unlink_action()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    jasper_abs_product_name = fields.Char(compute='_compute_jasper_abs_line')
    jasper_abs_price_unit = fields.Float(compute='_compute_jasper_abs_line')
    jasper_abs_discount = fields.Float(compute='_compute_jasper_abs_line')

    @api.depends('product_id', 'name', 'price_unit', 'tax_ids', 'discount')
    def _compute_jasper_abs_line(self):
        for line in self:
            line.jasper_abs_product_name = line.product_id.name or line.name or ''
            # price_unit_no_vat ของ npd_rent_price_round (o14): ถอด VAT เมื่อใช้สูตรใหม่ + VAT 7% รวมในราคา
            # + ไม่ใช่ราคาบ้านเขียว; o18 ยังไม่มีแฟล็กสองตัวนี้ -> ถือว่าสูตรใหม่ ไม่ใช่บ้านเขียว
            move = line.move_id
            use_new_calc = getattr(move, 'use_new_calc', True)
            use_baan_kheaw = getattr(move, 'use_baan_kheaw', False)
            has_vat_7_incl = any(t.price_include and abs(t.amount - 7.0) < 0.01 for t in line.tax_ids)
            price_unit = line.price_unit or 0.0
            if use_new_calc and has_vat_7_incl and not use_baan_kheaw:
                price_unit = round(price_unit / 1.07, 2)
            line.jasper_abs_price_unit = price_unit
            # o14 ใช้ discount_amount ของ bi_sale_purchase_discount_with_tax (o18 ไม่ได้ติดตั้ง) -> ส่วนลด % มาตรฐาน
            line.jasper_abs_discount = getattr(line, 'discount_amount', 0.0) or line.discount or 0.0
