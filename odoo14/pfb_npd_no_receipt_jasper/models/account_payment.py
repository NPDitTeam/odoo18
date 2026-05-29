import base64
import logging

from odoo import models, fields, api, tools

_logger = logging.getLogger(__name__)

THAI_MONTHS_SHORT = {
    1: 'ม.ค.', 2: 'ก.พ.', 3: 'มี.ค.', 4: 'เม.ย.',
    5: 'พ.ค.', 6: 'มิ.ย.', 7: 'ก.ค.', 8: 'ส.ค.',
    9: 'ก.ย.', 10: 'ต.ค.', 11: 'พ.ย.', 12: 'ธ.ค.',
}

SIGNATURE_RESOURCE_PATH = (
    'pfb_npd_no_receipt_jasper/static/img/Signature.png'
)

# Bank account info per company name (matching Odoo 14 logic from QWeb)
COMPANY_BANK_MAP = [
    ('นภดล อินเตอร์เทรดดิ้ง', 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-546107-1'),
    ('นภดล กรุงเทพ', 'บริษัท นภดล กรุงเทพ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 186-224773-9'),
    ('นภดล เอส กรุ๊ป', 'บริษัท นภดล เอส กรุ๊ป จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 180-210348-2'),
    ('เอ็นพีดี โลจิสติกส์', 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 439-044811-6'),
    ('เอ็นพีดี สตีลเทค', 'บริษัท เอ็นพีดี สตีลเทค จำกัด ธนาคารไทยพาณิชย์ เลขที่บัญชี 408-582058-4'),
]

# Cheque payable name per company
COMPANY_CHEQUE_PAYEE_MAP = [
    ('นภดล อินเตอร์เทรดดิ้ง', 'บริษัท นภดล อินเตอร์เทรดดิ้ง จำกัด'),
    ('นภดล กรุงเทพ', 'บริษัท นภดล กรุงเทพ จำกัด'),
    ('นภดล เอส กรุ๊ป', 'บริษัท นภดล เอส กรุ๊ป จำกัด'),
    ('เอ็นพีดี โลจิสติกส์', 'บริษัท เอ็นพีดี โลจิสติกส์ จำกัด'),
    ('เอ็นพีดี สตีลเทค', 'บริษัท เอ็นพีดี สตีลเทค จำกัด'),
]


def _format_thai_date(dt):
    if not dt:
        return ''
    day = dt.strftime('%d')
    month = THAI_MONTHS_SHORT.get(dt.month, '')
    year_short = str(dt.year + 543)[-2:]
    return '{} {} {}'.format(day, month, year_short)


def _join_address(*parts):
    return ' '.join(p for p in parts if p)


def _safe(obj, attr, default=''):
    if not obj:
        return default
    try:
        v = getattr(obj, attr, default)
    except Exception:
        return default
    if v is False or v is None:
        return default
    return v


def _bank_info_from_company(company_name):
    if not company_name:
        return ''
    for key, info in COMPANY_BANK_MAP:
        if key in company_name:
            return info
    return ''


def _cheque_payee_from_company(company_name):
    if not company_name:
        return ''
    for key, payee in COMPANY_CHEQUE_PAYEE_MAP:
        if key in company_name:
            return payee
    return ''


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # ---- Company / partner display fields ----
    jasper_no_company_name_display = fields.Char(
        compute='_compute_jasper_no_company_name_display',
    )
    jasper_no_company_address = fields.Char(
        compute='_compute_jasper_no_company_address',
    )
    jasper_no_branch_address = fields.Char(
        compute='_compute_jasper_no_branch_address',
    )
    jasper_no_partner_full_address = fields.Char(
        compute='_compute_jasper_no_partner_full_address',
    )
    jasper_no_partner_vat_branch = fields.Char(
        compute='_compute_jasper_no_partner_vat_branch',
    )

    # ---- Document number / date ----
    jasper_no_move_name = fields.Char(
        compute='_compute_jasper_no_move_name',
    )
    jasper_no_date_thai = fields.Char(
        compute='_compute_jasper_no_date_thai',
    )
    jasper_no_date_numeric = fields.Char(
        compute='_compute_jasper_no_date_numeric',
    )

    # ---- Payment method flags (✓ if selected) ----
    jasper_no_is_cash = fields.Char(
        compute='_compute_jasper_no_payment_flags',
    )
    jasper_no_is_bank = fields.Char(
        compute='_compute_jasper_no_payment_flags',
    )
    jasper_no_is_cheque = fields.Char(
        compute='_compute_jasper_no_payment_flags',
    )

    # ---- Aggregated amounts from custom_invoice_ids ----
    jasper_no_amount_untaxed = fields.Float(
        compute='_compute_jasper_no_amounts',
    )
    jasper_no_amount_tax = fields.Float(
        compute='_compute_jasper_no_amounts',
    )
    jasper_no_amount_total = fields.Float(
        compute='_compute_jasper_no_amounts',
    )

    # ---- Baht text (Thai amount-to-text) for total ----
    jasper_no_baht_text = fields.Char(
        compute='_compute_jasper_no_baht_text',
    )

    # ---- Cheque payable name + bank info per company ----
    jasper_no_cheque_payee = fields.Char(
        compute='_compute_jasper_no_company_bank_info',
    )
    jasper_no_bank_info = fields.Char(
        compute='_compute_jasper_no_company_bank_info',
    )

    # ---- Flat list of all invoice line items from linked invoices ----
    jasper_no_invoice_lines = fields.Many2many(
        'account.move.line',
        compute='_compute_jasper_no_invoice_lines',
    )

    # ---- Signature image ----
    jasper_no_signature = fields.Binary(
        compute='_compute_jasper_no_signature',
    )

    # =================================================================
    # Compute methods
    # =================================================================

    @api.depends('company_id.name')
    def _compute_jasper_no_company_name_display(self):
        for rec in self:
            name = rec.company_id.name or ''
            rec.jasper_no_company_name_display = (
                '{} (สำนักงานใหญ่)'.format(name) if name else ''
            )

    @api.depends(
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id', 'company_id.zip',
    )
    def _compute_jasper_no_company_address(self):
        for rec in self:
            c = rec.company_id
            state_name = c.state_id.name if c.state_id else ''
            rec.jasper_no_company_address = _join_address(
                c.street, c.street2, c.city, state_name, c.zip,
            )

    @api.depends(
        'branch_id', 'branch_id.street', 'branch_id.street2',
        'branch_id.city', 'branch_id.state_id', 'branch_id.zip',
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id', 'company_id.zip',
    )
    def _compute_jasper_no_branch_address(self):
        for rec in self:
            branch = rec.branch_id
            if branch:
                state_name = branch.state_id.name if branch.state_id else ''
                addr = _join_address(
                    branch.street, branch.street2, branch.city,
                    state_name, branch.zip,
                )
                if addr:
                    rec.jasper_no_branch_address = addr
                    continue
            c = rec.company_id
            state_name = c.state_id.name if c.state_id else ''
            rec.jasper_no_branch_address = _join_address(
                c.street, c.street2, c.city, state_name, c.zip,
            )

    @api.depends(
        'partner_id.street', 'partner_id.street2',
        'partner_id.city', 'partner_id.state_id', 'partner_id.zip',
    )
    def _compute_jasper_no_partner_full_address(self):
        for rec in self:
            p = rec.partner_id
            state_name = p.state_id.name if p.state_id else ''
            rec.jasper_no_partner_full_address = _join_address(
                p.street, p.street2, p.city, state_name, p.zip,
            )

    @api.depends('partner_id.vat')
    def _compute_jasper_no_partner_vat_branch(self):
        for rec in self:
            vat = rec.partner_id.vat or ''
            rec.jasper_no_partner_vat_branch = (
                '{} สำนักงานใหญ่'.format(vat) if vat else ''
            )

    @api.depends('move_id.name', 'name')
    def _compute_jasper_no_move_name(self):
        for rec in self:
            move_name = _safe(rec.move_id, 'name', '')
            payment_name = rec.name or ''
            # Skip incomplete journal sequence like "RV-" or "/" placeholder
            if move_name and not move_name.endswith('-') and move_name != '/':
                rec.jasper_no_move_name = move_name
            else:
                rec.jasper_no_move_name = payment_name or move_name or ''

    @api.depends('date')
    def _compute_jasper_no_date_thai(self):
        for rec in self:
            rec.jasper_no_date_thai = _format_thai_date(rec.date)

    @api.depends('date')
    def _compute_jasper_no_date_numeric(self):
        for rec in self:
            if rec.date:
                rec.jasper_no_date_numeric = rec.date.strftime('%d/%m/%Y')
            else:
                rec.jasper_no_date_numeric = ''

    def _compute_jasper_no_payment_flags(self):
        CHECK = '\u2713'
        for rec in self:
            is_cash = False
            is_bank = False
            is_cheque = False
            # Multi payment via paid_ids
            if getattr(rec, 'is_payment_multi', False):
                for p in rec.paid_ids:
                    t = getattr(p, 'payment_method_type', '') or ''
                    if t == 'cash':
                        is_cash = True
                    elif t == 'bank':
                        is_bank = True
                    elif t == 'cheque':
                        is_cheque = True
            else:
                # Single: payment_method_one_id.type (Odoo 14 custom field)
                p1 = getattr(rec, 'payment_method_one_id', False)
                t = ''
                if p1:
                    t = getattr(p1, 'type', '') or ''
                if t == 'cash':
                    is_cash = True
                elif t == 'bank':
                    is_bank = True
                elif t == 'cheque':
                    is_cheque = True
                else:
                    # Fallback: cheque_id direct or journal type
                    if getattr(rec, 'cheque_id', False):
                        is_cheque = True
                    else:
                        j_type = (rec.journal_id.type or '') if rec.journal_id else ''
                        if j_type == 'cash':
                            is_cash = True
                        elif j_type == 'bank':
                            is_bank = True
            rec.jasper_no_is_cash = CHECK if is_cash else ''
            rec.jasper_no_is_bank = CHECK if is_bank else ''
            rec.jasper_no_is_cheque = CHECK if is_cheque else ''

    @api.depends(
        'custom_invoice_ids',
        'custom_invoice_ids.move_id.amount_untaxed',
        'custom_invoice_ids.move_id.amount_tax',
        'custom_invoice_ids.move_id.amount_total',
    )
    def _compute_jasper_no_amounts(self):
        for rec in self:
            untaxed = 0.0
            tax = 0.0
            total = 0.0
            for inv_line in rec.custom_invoice_ids:
                move = inv_line.move_id
                if move:
                    untaxed += move.amount_untaxed or 0.0
                    tax += move.amount_tax or 0.0
                    total += move.amount_total or 0.0
            rec.jasper_no_amount_untaxed = untaxed
            rec.jasper_no_amount_tax = tax
            rec.jasper_no_amount_total = total

    @api.depends('jasper_no_amount_total')
    def _compute_jasper_no_baht_text(self):
        try:
            from bahttext import bahttext
        except ImportError:
            bahttext = None
        for rec in self:
            total = rec.jasper_no_amount_total or 0.0
            if bahttext:
                rec.jasper_no_baht_text = bahttext(total)
            else:
                rec.jasper_no_baht_text = '{:,.2f}'.format(total)

    @api.depends('company_id.name')
    def _compute_jasper_no_company_bank_info(self):
        for rec in self:
            cn = rec.company_id.name or ''
            rec.jasper_no_cheque_payee = _cheque_payee_from_company(cn)
            rec.jasper_no_bank_info = _bank_info_from_company(cn)

    @api.depends(
        'custom_invoice_ids',
        'custom_invoice_ids.move_id.invoice_line_ids',
    )
    def _compute_jasper_no_invoice_lines(self):
        # Display types to skip (section/note are display-only)
        SKIP_TYPES = ('line_section', 'line_note')
        AML = self.env['account.move.line']
        for rec in self:
            lines = AML
            for inv_line in rec.custom_invoice_ids:
                move = inv_line.move_id
                if not move:
                    continue
                for ml in move.invoice_line_ids:
                    dt = getattr(ml, 'display_type', False)
                    if dt in SKIP_TYPES:
                        continue
                    lines |= ml
            _logger.warning(
                '[jasper_no] invoice_lines for %s: count=%s ids=%s '
                '(custom_invoice_ids=%s)',
                rec, len(lines), lines.ids,
                rec.custom_invoice_ids.ids if rec.custom_invoice_ids else [],
            )
            rec.jasper_no_invoice_lines = lines

    def _compute_jasper_no_signature(self):
        signature_b64 = False
        try:
            with tools.file_open(SIGNATURE_RESOURCE_PATH, 'rb') as f:
                signature_b64 = base64.b64encode(f.read())
        except Exception as e:
            _logger.warning('Could not load signature image: %s', e)
        for rec in self:
            rec.jasper_no_signature = signature_b64
