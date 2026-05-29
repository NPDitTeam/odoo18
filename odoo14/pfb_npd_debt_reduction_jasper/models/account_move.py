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
        for rec in self:
            name = rec.company_id.name or ''
            rec.jasper_dr_company_name_display = (
                '{} (สำนักงานใหญ่)'.format(name) if name else ''
            )

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
        for rec in self:
            amount = rec.amount_untaxed or 0.0
            if bahttext:
                rec.jasper_dr_baht_text = bahttext(amount)
            else:
                rec.jasper_dr_baht_text = '{:,.2f}'.format(amount)

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
