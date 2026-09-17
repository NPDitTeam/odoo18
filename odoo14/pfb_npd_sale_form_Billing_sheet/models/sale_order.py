# -*- coding: utf-8 -*-
import re
import base64
import logging
from decimal import Decimal, ROUND_HALF_UP

from markupsafe import Markup

from odoo import fields, models
from odoo.tools.misc import file_path

_logger = logging.getLogger(__name__)

# หมายเหตุการตั้งชื่อเมธอด:
# โมดูลใบวางบิลอื่นก็ inherit sale.order เหมือนกัน Odoo รวมทุกโมดูลเป็นคลาสเดียว
# เมธอดชื่อซ้ำจะทับกันโดยไม่มีคำเตือน เมธอดที่รายงานของโมดูลนี้เรียกใช้จึงลงท้ายด้วย _billing_sheet

# ข้อมูลการชำระเงินของแต่ละบริษัท
# o14 แยกตามชื่อฐานข้อมูล (request.db) เพราะหนึ่งฐาน = หนึ่งบริษัท
# o18 ทุกบริษัทอยู่ฐานเดียว จึงเลือกจาก "ชื่อบริษัทของเอกสาร" แทน (ใช้ได้ทั้ง NPD_Logistics และ NPD_S_Group)
# ข้อความคัดลอกมาจาก o14 ตรงตัว
PAYMENT_INFO = [
    {
        'keyword': 'เอส กรุ๊ป',
        'account': 'บริษัท นภดล เอส กรุ๊ป จํากัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-222160-2',
        'payee': 'บริษัท นภดล เอส กรุ๊ป จํากัด',
        'qr_image': 'qr_sgroup.png',
        # o14 ฐาน NPD_S_Group_New_V2 ไม่แสดงเลขประจำตัวผู้เสียภาษีบนหัวเอกสาร
        'hide_vat': True,
    },
    {
        'keyword': 'สตีลเทค',
        'account': 'บริษัท เอ็นพีดี สตีลเทค จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-582058-4',
        'payee': 'บริษัท เอ็นพีดี สตีลเทค จำกัด',
        'qr_image': 'qr_steeltech.png',
    },
    {
        'keyword': 'โลจิสติกส์',
        'account': 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6',
        'payee': 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด',
        'qr_image': 'qr_logistics.png',
    },
    {
        'keyword': 'อินเตอร์เทรดดิ้ง',
        'account': 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-546107-1',
        'payee': 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด',
        'qr_image': 'qr_intertrading.png',
    },
    {
        'keyword': 'กรุงเทพ',
        'account': 'บริษัท นภดล กรุงเทพ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-224773-9',
        'payee': 'บริษัท นภดล กรุงเทพ จำกัด',
        'qr_image': 'qr_bangkok.png',
    },
]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # o14 ช่องนี้อยู่ในโมดูล custom_invoice_date ซึ่ง o18 ยังไม่ได้พอร์ต จึงประกาศไว้ที่นี่
    # (ถ้าพอร์ตโมดูลนั้นมาภายหลัง นิยามชื่อเดียวกันชนิดเดียวกัน Odoo จะรวมกันได้)
    partner_company_type = fields.Selection(
        related='partner_id.company_type',
        string='ประเภทลูกค้า',
        readonly=True)
    use_wht_billing_sheet = fields.Boolean(
        string='ใช้ภาษีหัก ณ ที่จ่ายใบแจ้งหนี้/ใบวางบิล หัก 5%',
        default=False,
        copy=False,
        help='ถ้าติ๊ก: ใบแจ้งหนี้/ใบวางบิล จะหักภาษี ณ ที่จ่าย 5% ของยอดค่าเช่าก่อนภาษีมูลค่าเพิ่ม '
             '(ไม่รวมค่าประกัน) ออกจากจำนวนเงินทั้งสิ้น จำนวนเงินตัวอักษร และยอดในคิวอาร์ '
             'พร้อมแสดงข้อมูลภาษีหัก ณ ที่จ่ายท้ายเอกสาร\n'
             'ถ้าไม่ติ๊ก: แสดงยอดเต็ม ไม่หักภาษี ณ ที่จ่าย')

    # ------------------------------------------------------------------
    # ยอดเงิน (สูตรเดียวกับ o14)
    # ------------------------------------------------------------------
    def get_grand_total_billing_sheet(self):
        """จำนวนเงินทั้งสิ้น ยอดเดียวที่ใช้ทั้งเอกสาร (ตัวเลขท้ายเอกสาร ตัวอักษร และคิวอาร์)

           - มี deposit_ref = เก็บค่าประกันไปแล้ว จึงไม่บวกค่าประกันซ้ำ
           - ไม่ติ๊ก 'ใช้ภาษีหัก ณ ที่จ่ายใบแจ้งหนี้/ใบวางบิล หัก 5%' (ค่าเริ่มต้น) = ยอดเต็ม
           - ติ๊ก = หักภาษี ณ ที่จ่าย 5% ออกจากยอดให้เลย ลูกค้าจ่ายยอดสุทธิ"""
        self.ensure_one()
        total = Decimal(str(self.amount_total if self.deposit_ref
                            else (self.pfb_amount or 0.0) + self.amount_total))
        if self.deduct_wht_billing_sheet():
            total -= Decimal(str(self.get_wht_amount_billing_sheet()))
        return float(total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def get_deposit_billing_sheet(self):
        """ค่าประกันที่แสดงท้ายเอกสาร — มี deposit_ref แปลว่าเก็บไปแล้ว แสดง 0"""
        self.ensure_one()
        return 0.0 if self.deposit_ref else (self.pfb_amount or 0.0)

    def get_rent_per_day_billing_sheet(self):
        """ค่าเช่าต่อวัน = amount_total / จำนวนวันเช่า (o14 หารตรง ๆ ถ้าวันเป็น 0 จะพัง)"""
        self.ensure_one()
        days = self.pfb_date_of_rent or 0
        return self.amount_total / days if days else self.amount_total

    # ------------------------------------------------------------------
    # ภาษีหัก ณ ที่จ่าย (สูตรเดียวกับ o14)
    # ------------------------------------------------------------------
    def get_wht_base_billing_sheet(self):
        """ฐานคำนวณภาษีหัก ณ ที่จ่าย = ยอดค่าเช่าก่อนภาษีมูลค่าเพิ่มเท่านั้น (ไม่รวมค่าประกัน)"""
        self.ensure_one()
        return self.amount_untaxed

    def get_wht_amount_billing_sheet(self):
        """ภาษีหัก ณ ที่จ่าย 5% ปัดแบบ round-half-up (เช่น 353.025 -> 353.03)"""
        base = Decimal(str(self.get_wht_base_billing_sheet()))
        wht = (base * Decimal('0.05')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return float(wht)

    def get_wht_amount(self):
        # คงชื่อเดิมไว้เผื่อมีที่อื่นเรียกใช้
        return self.get_wht_amount_billing_sheet()

    def wht_applies_billing_sheet(self):
        """คิดภาษีหัก ณ ที่จ่ายเฉพาะลูกค้านิติบุคคล"""
        self.ensure_one()
        return self.partner_id.company_type == 'company'

    def deduct_wht_billing_sheet(self):
        """ติ๊ก 'ใช้ภาษีหัก ณ ที่จ่ายใบแจ้งหนี้/ใบวางบิล หัก 5%' = หัก 5% ออกจากยอด"""
        self.ensure_one()
        return self.wht_applies_billing_sheet() and bool(self.use_wht_billing_sheet)

    # ------------------------------------------------------------------
    # QR พร้อมเพย์ (มาตรฐาน EMVCo / Thai QR Payment) — เหมือน o14
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

    def _promptpay_account_billing_sheet(self):
        """คืน (sub-tag, ค่า) ของเลขพร้อมเพย์บริษัท โดยดูชนิดจากจำนวนหลัก
           15 หลัก = e-Wallet ID / 13 หลัก = เลขผู้เสียภาษี / 9-10 หลัก = เบอร์มือถือ (0066 + 9 หลักท้าย)"""
        digits = re.sub(r'\D', '', self.company_id.promptpay_id or '')
        if len(digits) == 15:
            return '03', digits
        if len(digits) == 13:
            return '02', digits
        if len(digits) in (9, 10):
            return '01', '0066' + digits[-9:]
        return '', ''

    def get_promptpay_qr_payload_billing_sheet(self):
        """สร้าง payload คิวอาร์พร้อมเพย์ ระบุยอด = จำนวนเงินทั้งสิ้น"""
        self.ensure_one()
        tag, account = self._promptpay_account_billing_sheet()
        if not account:
            return ''
        amount = '%.2f' % self.get_grand_total_billing_sheet()

        merchant = self._promptpay_tlv('00', 'A000000677010111')   # AID พร้อมเพย์
        merchant += self._promptpay_tlv(tag, account)

        payload = self._promptpay_tlv('00', '01')     # Payload Format Indicator
        payload += self._promptpay_tlv('01', '12')    # 12 = dynamic (ระบุยอดเงินมาแล้ว)
        payload += self._promptpay_tlv('29', merchant)
        payload += self._promptpay_tlv('53', '764')   # สกุลเงิน THB
        payload += self._promptpay_tlv('54', amount)  # จำนวนเงิน
        payload += self._promptpay_tlv('58', 'TH')    # ประเทศ
        payload += '6304'                             # tag CRC + ความยาว
        payload += self._promptpay_crc16(payload)
        return payload

    def get_promptpay_qr_image_billing_sheet(self):
        """รูปคิวอาร์เป็น base64 ถ้าบริษัทยังไม่ได้ตั้งเลขพร้อมเพย์จะคืนค่าว่าง"""
        payload = self.get_promptpay_qr_payload_billing_sheet()
        if not payload:
            return ''
        try:
            img = self.env['ir.actions.report'].barcode('QR', payload, width=220, height=220)
            return base64.b64encode(img).decode('ascii')
        except Exception as e:  # noqa: BLE001
            _logger.warning("promptpay QR error on %s: %s", self.name, e)
            return ''

    # ------------------------------------------------------------------
    # ข้อมูลตามบริษัท / สาขา (แทน request.db และ user.branch_id.address ของ o14)
    # ------------------------------------------------------------------
    def _payment_info_billing_sheet(self):
        self.ensure_one()
        name = self.company_id.name or ''
        for info in PAYMENT_INFO:
            if info['keyword'] in name:
                return info
        return {}

    def get_payment_account_billing_sheet(self):
        return self._payment_info_billing_sheet().get('account', '')

    def get_payment_payee_billing_sheet(self):
        return self._payment_info_billing_sheet().get('payee', '')

    def show_company_vat_billing_sheet(self):
        return not self._payment_info_billing_sheet().get('hide_vat')

    def get_fallback_qr_billing_sheet(self):
        """รูป QR เดิมของบริษัท (ใช้เมื่อบริษัทยังไม่ได้ตั้งเลขพร้อมเพย์) ฝังเป็น base64
           ไม่อ้าง URL ไม่ต้องพึ่งให้ wkhtmltopdf โหลดไฟล์เอง"""
        image = self._payment_info_billing_sheet().get('qr_image')
        if not image:
            return ''
        try:
            path = file_path('pfb_npd_sale_form_Billing_sheet/static/src/img/%s' % image)
            with open(path, 'rb') as handle:
                return base64.b64encode(handle.read()).decode('ascii')
        except Exception as e:  # noqa: BLE001
            _logger.warning("billing sheet fallback QR error on %s: %s", self.name, e)
            return ''

    def _branch_billing_sheet(self):
        """o14 ใช้สาขาของผู้พิมพ์ (user.branch_id) — o18 ใบสั่งขายมีสาขาของตัวเอง
           จึงใช้สาขาของเอกสารก่อน พิมพ์ซ้ำจากสำนักงานใหญ่ก็ยังได้ที่อยู่สาขาที่ถูกต้อง"""
        self.ensure_one()
        return self.branch_id or self.env.user.branch_id

    def get_branch_address_billing_sheet(self):
        """ที่อยู่หัวเอกสาร: สาขา -> ถ้าสาขาไม่มีที่อยู่ ใช้ที่อยู่บริษัท"""
        self.ensure_one()
        branch = self._branch_billing_sheet()
        parts = []
        if branch:
            parts = [branch.street, branch.street2, branch.city,
                     branch.state_id.name if branch.state_id else '', branch.zip]
        text = ' '.join(p for p in parts if p)
        if not text:
            company = self.company_id
            text = ' '.join(p for p in [company.street, company.street2, company.city,
                                        company.state_id.name if company.state_id else '',
                                        company.zip] if p)
        return text

    def is_head_office_billing_sheet(self):
        """o14 ใช้เบอร์โทรสาขา '00000' เป็นตัวบอกสำนักงานใหญ่ o18 มีช่องนี้ตรง ๆ"""
        branch = self._branch_billing_sheet()
        return bool(branch and getattr(branch, 'hr_is_head_office', False))

    # ------------------------------------------------------------------
    # อื่น ๆ
    # ------------------------------------------------------------------
    def get_invoice_names_billing_sheet(self):
        """เลขที่ใบแจ้งหนี้ — o14 ใช้ invoice_ids.name ตรง ๆ ซึ่งพังเมื่อมีหลายใบ
           (เช่นมีใบลดหนี้) จึงแสดงเฉพาะใบแจ้งหนี้ลูกค้าที่ไม่ถูกยกเลิก"""
        self.ensure_one()
        invoices = self._invoices_billing_sheet()
        return ', '.join(n for n in invoices.mapped('name') if n and n != '/')

    def _invoices_billing_sheet(self):
        invoices = self.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
        return invoices or self.invoice_ids

    def get_invoice_due_date_billing_sheet(self):
        self.ensure_one()
        dates = [d for d in self._invoices_billing_sheet().mapped('invoice_date_due') if d]
        return dates[0].strftime('%d-%m-%Y') if dates else ''

    def get_note_billing_sheet(self):
        """หมายเหตุแบบตัด <p> ออกเหมือน o14 (note เป็น Html ที่ผ่าน sanitize แล้ว)"""
        self.ensure_one()
        note = str(self.note or '')
        # คั่นย่อหน้าด้วยช่องว่าง ไม่งั้นข้อความสองย่อหน้าติดกันเป็นคำเดียว
        return Markup(note.replace('<p>', '').replace('</p>', ' ').strip())

    def get_total_baht_text_sheet(self):
        """จำนวนเงินทั้งสิ้นเป็นตัวอักษร — ใช้ l10n_th_amount_to_text แทนไลบรารี bahttext
           (เครื่อง o18 ไม่ได้ติดตั้ง bahttext) ผลลัพธ์รูปแบบเดียวกัน"""
        self.ensure_one()
        currency = self.currency_id or self.env.ref('base.THB')
        return currency.with_context(lang='th_TH').amount_to_text(
            self.get_grand_total_billing_sheet())
