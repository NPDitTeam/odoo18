import base64
import logging
import re

from odoo import models, fields, api, tools

_logger = logging.getLogger(__name__)

THAI_MONTHS_SHORT = {
    1: 'ม.ค.', 2: 'ก.พ.', 3: 'มี.ค.', 4: 'เม.ย.',
    5: 'พ.ค.', 6: 'มิ.ย.', 7: 'ก.ค.', 8: 'ส.ค.',
    9: 'ก.ย.', 10: 'ต.ค.', 11: 'พ.ย.', 12: 'ธ.ค.',
}

SIGNATURE_RESOURCE_PATH = (
    'pfb_npd_debt_reduction_jasper/static/img/Signature.png'
)


def _format_thai_date_short(dt):
    if not dt:
        return ''
    day = dt.strftime('%d')
    month = THAI_MONTHS_SHORT.get(dt.month, '')
    year_short = str(dt.year + 543)[-2:]
    return '{} {} {}'.format(day, month, year_short)


def _join_address(*parts):
    return ' '.join(p for p in parts if p)


def _strip_html(html):
    """Strip HTML tags and normalize whitespace."""
    if not html:
        return ''
    # Remove tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Decode common entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ---- Header / partner ----
    jasper_dr_company_name_display = fields.Char(
        compute='_compute_jasper_dr_company_name_display',
    )
    jasper_dr_branch_address = fields.Char(
        compute='_compute_jasper_dr_branch_address',
    )
    jasper_dr_partner_full_address = fields.Char(
        compute='_compute_jasper_dr_partner_full_address',
    )
    jasper_dr_partner_vat_branch = fields.Char(
        compute='_compute_jasper_dr_partner_vat_branch',
    )

    # ---- Dates (Thai short format) ----
    jasper_dr_date_thai = fields.Char(
        compute='_compute_jasper_dr_date_thai',
    )
    jasper_dr_invoice_date_thai = fields.Char(
        compute='_compute_jasper_dr_invoice_date_thai',
    )

    # ---- Reference invoice numbers (joined) ----
    jasper_dr_reference_invoice = fields.Char(
        compute='_compute_jasper_dr_reference_invoice',
    )
    # ลงวันที่ของใบรับชำระที่อ้างอิงจริง (ไม่ใช่วันที่ของใบลดหนี้เอง)
    jasper_dr_reference_date_thai = fields.Char(
        compute='_compute_jasper_dr_reference_date_thai',
    )

    # ---- รายการสินค้า: พิมพ์บรรทัดเดียวให้เหมือนใบกำกับภาษี/ใบเสร็จรับเงิน ----
    jasper_dr_line_description = fields.Char(
        compute='_compute_jasper_dr_line',
    )

    # ---- หมายเหตุที่ผู้ใช้กรอกเอง (ช่อง "เหตุผลในการลดหนี้") ----
    debt_reduction_note = fields.Text(
        string='หมายเหตุ',
        copy=False,
        help='หมายเหตุที่จะแสดงในช่อง "เหตุผลในการลดหนี้" บนแบบฟอร์มใบลดหนี้',
    )
    jasper_dr_note_text = fields.Char(
        compute='_compute_jasper_dr_note_text',
    )

    # ---- Amounts derived from credit note ----
    jasper_dr_amount_original = fields.Float(
        compute='_compute_jasper_dr_amounts',
    )
    jasper_dr_amount_correct = fields.Float(
        compute='_compute_jasper_dr_amounts',
    )
    jasper_dr_amount_diff = fields.Float(
        compute='_compute_jasper_dr_amounts',
    )
    jasper_dr_amount_vat = fields.Float(
        compute='_compute_jasper_dr_amounts',
    )

    # ---- Baht text from amount_untaxed (per Odoo 14 logic) ----
    jasper_dr_baht_text = fields.Char(
        compute='_compute_jasper_dr_baht_text',
    )

    # ---- Cleaned narration (HTML stripped) ----
    jasper_dr_narration_clean = fields.Char(
        compute='_compute_jasper_dr_narration_clean',
    )

    # ---- Signature image ----
    jasper_dr_signature = fields.Binary(
        compute='_compute_jasper_dr_signature',
    )

    # =================================================================
    # Compute methods
    # =================================================================

    @api.depends('company_id.name')
    def _compute_jasper_dr_company_name_display(self):
        # o14 พิมพ์ doc.company_id.name ตรง ๆ — เดิมต่อท้าย "(สำนักงานใหญ่)" เอง
        # ทำให้บริษัทที่ชื่อมีคำนี้อยู่แล้ว (อินเตอร์เทรดดิ้ง) ขึ้นซ้ำสองครั้ง
        for rec in self:
            rec.jasper_dr_company_name_display = rec.company_id.name or ''

    @api.depends(
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id', 'company_id.zip',
    )
    def _compute_jasper_dr_branch_address(self):
        for rec in self:
            # Try branch_id first if it exists (multi_branch_management_aagam)
            try:
                branch = rec.branch_id
            except Exception:
                branch = False
            if branch:
                state_name = branch.state_id.name if branch.state_id else ''
                addr = _join_address(
                    branch.street, branch.street2, branch.city,
                    state_name, branch.zip,
                )
                if addr:
                    rec.jasper_dr_branch_address = addr
                    continue
            c = rec.company_id
            state_name = c.state_id.name if c.state_id else ''
            rec.jasper_dr_branch_address = _join_address(
                c.street, c.street2, c.city, state_name, c.zip,
            )

    @api.depends(
        'partner_id.street', 'partner_id.street2',
        'partner_id.city', 'partner_id.state_id', 'partner_id.zip',
    )
    def _compute_jasper_dr_partner_full_address(self):
        for rec in self:
            p = rec.partner_id
            state_name = p.state_id.name if p.state_id else ''
            rec.jasper_dr_partner_full_address = _join_address(
                p.street, p.street2, p.city, state_name, p.zip,
            )

    @api.depends('partner_id.vat')
    def _compute_jasper_dr_partner_vat_branch(self):
        for rec in self:
            rec.jasper_dr_partner_vat_branch = rec.partner_id.vat or ''

    @api.depends('date')
    def _compute_jasper_dr_date_thai(self):
        for rec in self:
            rec.jasper_dr_date_thai = _format_thai_date_short(rec.date)

    @api.depends('invoice_date')
    def _compute_jasper_dr_invoice_date_thai(self):
        for rec in self:
            rec.jasper_dr_invoice_date_thai = _format_thai_date_short(rec.invoice_date)

    @api.depends('reversed_entry_id')
    def _compute_jasper_dr_reference_invoice(self):
        for rec in self:
            text = ''
            try:
                rev = rec.reversed_entry_id
                if rev:
                    payments = rev._get_reconciled_payments().filtered(
                        lambda p: p.state == 'posted'
                    )
                    if payments:
                        text = ', '.join(payments.mapped('name'))
                    else:
                        # Fall back to the original invoice's name
                        text = rev.name or ''
            except Exception as e:
                _logger.warning('reversed_entry_id payments lookup failed: %s', e)
            if not text:
                text = 'ไม่พบข้อมูลการรับชำระ'
            rec.jasper_dr_reference_invoice = text

    def get_reference_payments_debt_reduction(self):
        """ใบรับชำระ (CUST.IN) ที่ใบกำกับภาษีต้นทางของใบลดหนี้อ้างอิงอยู่"""
        self.ensure_one()
        if not self.reversed_entry_id:
            return self.env['account.payment']
        try:
            return self.reversed_entry_id._get_reconciled_payments().filtered(
                lambda p: p.state == 'posted'
            )
        except Exception as e:      # กันเคสข้อมูลเก่า/โมดูลบัญชีเปลี่ยน API
            _logger.warning('reversed_entry_id payments lookup failed: %s', e)
            return self.env['account.payment']

    @api.depends('reversed_entry_id', 'invoice_date')
    def _compute_jasper_dr_reference_date_thai(self):
        """ลงวันที่ = วันที่ของใบรับชำระที่อ้างอิง ถ้าไม่พบจึงใช้วันที่ของใบลดหนี้

        เดิมใช้ invoice_date ของใบลดหนี้เอง ทำให้วันที่ไม่ตรงกับเลข CUST.IN
        ที่พิมพ์คู่กันในบรรทัดเดียวกัน
        """
        for rec in self:
            dates = []
            for payment_date in rec.get_reference_payments_debt_reduction().mapped('date'):
                if payment_date and payment_date not in dates:
                    dates.append(payment_date)
            if not dates and rec.invoice_date:
                dates = [rec.invoice_date]
            rec.jasper_dr_reference_date_thai = ', '.join(
                _format_thai_date_short(d) for d in dates
            )

    @api.depends('amount_untaxed')
    def _compute_jasper_dr_line(self):
        """ใบลดหนี้พิมพ์รายการเดียว ไม่ไล่ทีละบรรทัดสินค้า

        ทีมบัญชีปรับที่ Odoo 14 ให้เหมือนใบกำกับภาษี/ใบเสร็จรับเงิน
        (เดิมโชว์ IRAA-0302, IRAA-0303 ... ทีละแถว)
        """
        for rec in self:
            rec.jasper_dr_line_description = 'ค่าเช่าเครื่องมือก่อสร้าง'

    @api.depends('debt_reduction_note')
    def _compute_jasper_dr_note_text(self):
        """ช่อง "เหตุผลในการลดหนี้" อ่านจากแถบหมายเหตุของเอกสาร

        ไม่ fallback ไป narration เพราะ narration เก็บข้อความเงื่อนไขมาตรฐาน
        (ห้ามตัด ห้ามเชื่อม / ราคาไม่รวมค่าขนส่ง ...) แล้วไปโผล่ผิดช่อง
        ใบเก่าที่ยังไม่กรอกหมายเหตุจึงพิมพ์ช่องนี้ว่าง — ตั้งใจให้เป็นแบบนั้น
        """
        for rec in self:
            rec.jasper_dr_note_text = (rec.debt_reduction_note or '').strip()

    @api.depends(
        'reversed_entry_id.amount_total',
        'amount_untaxed', 'amount_total', 'amount_tax',
    )
    def _compute_jasper_dr_amounts(self):
        for rec in self:
            rev = rec.reversed_entry_id
            original_total = (rev.amount_total if rev else 0.0) or 0.0
            total = rec.amount_total or 0.0
            rec.jasper_dr_amount_original = original_total
            # มูลค่าที่ถูกต้อง = original − amount_total (per latest Odoo 14 logic)
            rec.jasper_dr_amount_correct = original_total - total
            # ผลต่าง = amount_total
            rec.jasper_dr_amount_diff = total
            # ภาษีมูลค่าเพิ่ม 7% = ใช้ amount_tax จริง
            rec.jasper_dr_amount_vat = rec.amount_tax or 0.0

    @api.depends('amount_untaxed')
    def _compute_jasper_dr_baht_text(self):
        try:
            from bahttext import bahttext
        except ImportError:
            bahttext = None
        thb = self.env.ref('base.THB', raise_if_not_found=False)
        for rec in self:
            amount = rec.amount_untaxed or 0.0
            if bahttext:
                rec.jasper_dr_baht_text = bahttext(amount)
            else:
                # เครื่อง o18 ไม่มี bahttext (เดิม fallback เป็นตัวเลข "403.74") -> ใช้ l10n_th_amount_to_text
                currency = rec.currency_id or thb
                rec.jasper_dr_baht_text = currency.with_context(lang='th_TH').amount_to_text(amount)

    @api.depends('narration')
    def _compute_jasper_dr_narration_clean(self):
        for rec in self:
            rec.jasper_dr_narration_clean = _strip_html(rec.narration or '')

    def _compute_jasper_dr_signature(self):
        signature_b64 = False
        try:
            with tools.file_open(SIGNATURE_RESOURCE_PATH, 'rb') as f:
                signature_b64 = base64.b64encode(f.read())
        except Exception as e:
            _logger.warning('Could not load signature image: %s', e)
        for rec in self:
            rec.jasper_dr_signature = signature_b64
