import re
import base64
import logging
from decimal import Decimal, ROUND_HALF_UP

from odoo import api, fields, models
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

# ข้อมูลการชำระเงินของแต่ละบริษัท
# O14 เลือกด้วย request.db (แยก DB ต่อบริษัท) -> O18 single-DB เลือกด้วย
# บริษัทที่กำลังใช้งาน (env.company) โดย match จาก token ในชื่อบริษัท
# (แบบเดียวกับใบกำกับการเช่า / ใบเสนอราคาเช่า Jasper) ข้อความคัดลอกจาก o14 ตรงตัว
PAYMENT_INFO = [
    {
        'token': 'กรุ๊ป',
        'account': 'บริษัท นภดล เอส กรุ๊ป จํากัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-222160-2',
        'payee': 'บริษัท นภดล เอส กรุ๊ป จํากัด',
        'qr_image': 'qr_sgroup.png',
        # o14 ฐาน NPD_S_Group_New_V2 ไม่แสดงเลขประจำตัวผู้เสียภาษีบนหัวเอกสาร
        'hide_vat': True,
    },
    {
        'token': 'สตีลเทค',
        'account': 'บริษัท เอ็นพีดี สตีลเทค จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-582058-4',
        'payee': 'บริษัท เอ็นพีดี สตีลเทค จำกัด',
        'qr_image': 'qr_steeltech.png',
    },
    {
        'token': 'โลจิสติกส์',
        'account': 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6',
        'payee': 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด',
        'qr_image': 'qr_logistics.png',
    },
    {
        'token': 'อินเตอร์เทรดดิ้ง',
        'account': 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-546107-1',
        'payee': 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด',
        'qr_image': 'qr_intertrading.png',
    },
    {
        'token': 'กรุงเทพ',
        'account': 'บริษัท นภดล กรุงเทพ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-224773-9',
        'payee': 'บริษัท นภดล กรุงเทพ จำกัด',
        'qr_image': 'qr_bangkok.png',
    },
]


def _fmt_date(value):
    """รูปแบบวันที่ของใบวางบิล o14: dd-mm-YYYY (ค.ศ.)"""
    return value.strftime('%d-%m-%Y') if value else ''


def _money(value):
    return float(Decimal(str(value or 0.0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ช่องติ๊ก use_wht_billing_sheet อยู่ในโมดูล custom_invoice_date (เหมือน o14)

    # ------------------------------------------------------------------
    # ฟิลด์สำหรับ Jasper (ไม่เก็บลงฐาน) — ขึ้นต้น jasper_bs_ กันชนกับรายงาน Jasper ตัวอื่นบน sale.order
    # ------------------------------------------------------------------
    jasper_bs_company_id = fields.Many2one(
        'res.company', string='Billing Sheet Company', compute='_compute_jasper_bs_header')
    jasper_bs_company_name = fields.Char(compute='_compute_jasper_bs_header')
    jasper_bs_company_address = fields.Char(compute='_compute_jasper_bs_header')
    jasper_bs_company_vat_line = fields.Char(compute='_compute_jasper_bs_header')

    jasper_bs_invoice_names = fields.Char(compute='_compute_jasper_bs_document')
    jasper_bs_date_order = fields.Char(compute='_compute_jasper_bs_document')
    jasper_bs_due_date = fields.Char(compute='_compute_jasper_bs_document')
    jasper_bs_partner_address = fields.Char(compute='_compute_jasper_bs_document')
    jasper_bs_rent_line = fields.Char(compute='_compute_jasper_bs_document')
    jasper_bs_note = fields.Char(compute='_compute_jasper_bs_document')

    jasper_bs_rent_per_day = fields.Float(compute='_compute_jasper_bs_amounts')
    jasper_bs_deposit = fields.Float(compute='_compute_jasper_bs_amounts')
    jasper_bs_wht_base = fields.Float(compute='_compute_jasper_bs_amounts')
    jasper_bs_wht_amount = fields.Float(compute='_compute_jasper_bs_amounts')
    jasper_bs_grand_total = fields.Float(compute='_compute_jasper_bs_amounts')
    jasper_bs_baht_text = fields.Char(compute='_compute_jasper_bs_amounts')
    jasper_bs_wht_line = fields.Char(compute='_compute_jasper_bs_amounts')

    jasper_bs_payment_text = fields.Char(compute='_compute_jasper_bs_payment')
    jasper_bs_qr_title = fields.Char(compute='_compute_jasper_bs_payment')
    jasper_bs_qr_image = fields.Binary(compute='_compute_jasper_bs_payment', attachment=False)

    # ------------------------------------------------------------------
    # สูตรยอดเงิน (เหมือน o14)
    # ------------------------------------------------------------------
    def _bs_wht_applies(self):
        """คิดภาษีหัก ณ ที่จ่ายเฉพาะลูกค้านิติบุคคล"""
        self.ensure_one()
        return self.partner_id.company_type == 'company'

    def _bs_deduct_wht(self):
        """ติ๊ก 'ใช้ภาษีหัก ณ ที่จ่ายใบแจ้งหนี้/ใบวางบิล หัก 5%' = หัก 5% ออกจากยอด"""
        self.ensure_one()
        return self._bs_wht_applies() and bool(self.use_wht_billing_sheet)

    def _bs_wht_amount(self):
        """ภาษีหัก ณ ที่จ่าย 5% ของค่าเช่าก่อน VAT (ไม่รวมค่าประกัน) ปัด round-half-up"""
        self.ensure_one()
        base = Decimal(str(self.amount_untaxed or 0.0))
        return float((base * Decimal('0.05')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def _bs_grand_total(self):
        """จำนวนเงินทั้งสิ้น ยอดเดียวที่ใช้ทั้งเอกสาร (ตัวเลข ตัวอักษร และคิวอาร์)
           - มี deposit_ref = เก็บค่าประกันไปแล้ว จึงไม่บวกค่าประกันซ้ำ
           - ติ๊กหัก 5% = หักภาษี ณ ที่จ่ายออกจากยอดให้เลย"""
        self.ensure_one()
        total = Decimal(str(self.amount_total if self.deposit_ref
                            else (self.pfb_amount or 0.0) + self.amount_total))
        if self._bs_deduct_wht():
            total -= Decimal(str(self._bs_wht_amount()))
        return float(total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def _bs_payment_info(self):
        name = self.env.company.name or ''
        for info in PAYMENT_INFO:
            if info['token'] in name:
                return info
        return {}

    # ------------------------------------------------------------------
    # หัวกระดาษ: ใช้บริษัทที่กำลังเลือกอยู่ (active company / env.company)
    # เหมือนใบกำกับการเช่า / ใบเสนอราคาเช่า / ใบส่งของ Jasper
    # ------------------------------------------------------------------
    @staticmethod
    def _bs_join_address(parts):
        """ต่อที่อยู่โดยข้ามส่วนที่มีอยู่ในข้อความแล้ว
           (บางบริษัทพิมพ์ที่อยู่เต็มไว้ในช่องถนน พอต่อ จังหวัด/รหัสไปรษณีย์ซ้ำจะยาวจนตกบรรทัด)"""
        text = ''
        for part in parts:
            part = (part or '').strip()
            if not part:
                continue
            core = part[2:] if part.startswith('จ.') else part
            if core in text:
                continue
            text = ('%s %s' % (text, part)).strip()
        return text

    @api.depends_context('allowed_company_ids')
    def _compute_jasper_bs_header(self):
        company = self.env.company
        address = self._bs_join_address([
            company.street, company.street2, company.city,
            company.state_id.name if company.state_id else '', company.zip])
        head_office = '' if company.parent_id else ' (สำนักงานใหญ่)'
        info = self._bs_payment_info()
        vat_line = '' if info.get('hide_vat') else \
            'เลขประจำตัวผู้เสียภาษี %s%s' % (company.vat or '', head_office)
        for rec in self:
            rec.jasper_bs_company_id = company
            rec.jasper_bs_company_name = company.name or ''
            rec.jasper_bs_company_address = address
            rec.jasper_bs_company_vat_line = vat_line

    def _compute_jasper_bs_document(self):
        for rec in self:
            # o14 ใช้ invoice_ids.name ตรง ๆ ซึ่งพังเมื่อมีหลายใบ (เช่นมีใบลดหนี้)
            # แสดงเฉพาะใบแจ้งหนี้ลูกค้าที่ไม่ถูกยกเลิก
            invoices = rec.invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state != 'cancel') or rec.invoice_ids
            rec.jasper_bs_invoice_names = ', '.join(
                n for n in invoices.mapped('name') if n and n != '/')
            due_dates = [d for d in invoices.mapped('invoice_date_due') if d]
            rec.jasper_bs_due_date = _fmt_date(due_dates[0]) if due_dates else ''
            rec.jasper_bs_date_order = _fmt_date(rec.date_order)

            p = rec.partner_id
            rec.jasper_bs_partner_address = rec._bs_join_address([
                p.street, p.street2, p.city, p.state_id.name if p.state_id else '', p.zip])

            rec.jasper_bs_rent_line = 'ค่าเช่า เอกสารเลขที่ : %s\nวันที่ : %s  ถึงวันที่ : %s' % (
                rec.name or '', _fmt_date(rec.start_rent_date), _fmt_date(rec.end_rent_date))

            note = str(rec.note or '')
            note = re.sub(r'</p>\s*<p>', ' ', note)
            rec.jasper_bs_note = re.sub(r'<[^>]*>', '', note).strip()

    @api.depends_context('allowed_company_ids')
    def _compute_jasper_bs_amounts(self):
        for rec in self:
            days = rec.pfb_date_of_rent or 0
            # o14: amount_total / pfb_date_of_rent (ถ้าวันเป็น 0 o14 จะพัง)
            rec.jasper_bs_rent_per_day = rec.amount_total / days if days else rec.amount_total
            rec.jasper_bs_deposit = 0.0 if rec.deposit_ref else (rec.pfb_amount or 0.0)
            rec.jasper_bs_wht_base = _money(rec.amount_untaxed)
            rec.jasper_bs_wht_amount = rec._bs_wht_amount()
            grand_total = rec._bs_grand_total()
            rec.jasper_bs_grand_total = grand_total
            currency = rec.currency_id or self.env.ref('base.THB')
            rec.jasper_bs_baht_text = currency.with_context(lang='th_TH').amount_to_text(grand_total)

            # บล็อกภาษีหัก ณ ที่จ่าย แสดงทุกใบที่ลูกค้าเป็นนิติบุคคล (ติ๊ก = หักออกจากยอดแล้ว)
            if rec._bs_wht_applies():
                line = 'ภาษีหัก ณ ที่จ่าย 5%% ของ :     %s     =     %s     บาท' % (
                    '{:,.2f}'.format(rec.jasper_bs_wht_base), '{:,.2f}'.format(rec.jasper_bs_wht_amount))
                if rec._bs_deduct_wht():
                    line += '     (หักออกจากจำนวนเงินทั้งสิ้นแล้ว)'
                rec.jasper_bs_wht_line = line
            else:
                rec.jasper_bs_wht_line = ''

    # ------------------------------------------------------------------
    # การชำระเงิน + QR พร้อมเพย์ (มาตรฐาน EMVCo / Thai QR Payment เหมือน o14)
    # ------------------------------------------------------------------
    @staticmethod
    def _promptpay_tlv(tag, value):
        return '%s%02d%s' % (tag, len(value), value)

    @staticmethod
    def _promptpay_crc16(payload):
        """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)"""
        crc = 0xFFFF
        for ch in payload.encode('utf-8'):
            crc ^= ch << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
                crc &= 0xFFFF
        return '%04X' % crc

    def _bs_promptpay_payload(self, company):
        """payload คิวอาร์พร้อมเพย์ ระบุยอด = จำนวนเงินทั้งสิ้น
           15 หลัก = e-Wallet / 13 หลัก = เลขผู้เสียภาษี / 9-10 หลัก = เบอร์มือถือ (0066 + 9 หลักท้าย)"""
        self.ensure_one()
        digits = re.sub(r'\D', '', company.promptpay_id or '')
        if len(digits) == 15:
            tag, account = '03', digits
        elif len(digits) == 13:
            tag, account = '02', digits
        elif len(digits) in (9, 10):
            tag, account = '01', '0066' + digits[-9:]
        else:
            return ''
        merchant = self._promptpay_tlv('00', 'A000000677010111') + self._promptpay_tlv(tag, account)
        payload = self._promptpay_tlv('00', '01')      # Payload Format Indicator
        payload += self._promptpay_tlv('01', '12')     # 12 = dynamic (ระบุยอดเงินมาแล้ว)
        payload += self._promptpay_tlv('29', merchant)
        payload += self._promptpay_tlv('53', '764')    # สกุลเงิน THB
        payload += self._promptpay_tlv('54', '%.2f' % self._bs_grand_total())
        payload += self._promptpay_tlv('58', 'TH')     # ประเทศ
        payload += '6304'
        return payload + self._promptpay_crc16(payload)

    def _bs_fallback_qr(self, info):
        """รูป QR เดิมของบริษัท (ใช้เมื่อบริษัทยังไม่ได้ตั้งเลขพร้อมเพย์)"""
        if not info.get('qr_image'):
            return False
        try:
            path = file_path('pfb_npd_sale_form_Billing_sheet_jasper/static/src/img/%s' % info['qr_image'])
            with open(path, 'rb') as handle:
                return base64.b64encode(handle.read())
        except Exception as e:  # noqa: BLE001
            _logger.warning("billing sheet fallback QR error: %s", e)
            return False

    @api.depends_context('allowed_company_ids')
    def _compute_jasper_bs_payment(self):
        company = self.env.company
        info = self._bs_payment_info()
        lines = []
        if info:
            lines.append('โอนเงินเข้าบัญชี : %s' % info['account'])
            lines.append('สั่งจ่ายด้วยเช็คกรุณาสั่งจ่ายในนาม : %s' % info['payee'])
        lines.append('ค่าธรรมเนียมธนาคาร ผู้ชำระเงินเป็นผู้รับผิดชอบ')
        payment_text = '\n'.join(lines)
        fallback = None
        for rec in self:
            rec.jasper_bs_payment_text = payment_text
            image = False
            title = ''
            payload = rec._bs_promptpay_payload(company)
            if payload:
                try:
                    png = self.env['ir.actions.report'].barcode('QR', payload, width=220, height=220)
                    image = base64.b64encode(png)
                    title = 'สแกนจ่ายด้วยพร้อมเพย์'
                except Exception as e:  # noqa: BLE001
                    _logger.warning("promptpay QR error on %s: %s", rec.name, e)
            if not image:
                if fallback is None:
                    fallback = self._bs_fallback_qr(info)
                image = fallback
            rec.jasper_bs_qr_image = image
            rec.jasper_bs_qr_title = title
