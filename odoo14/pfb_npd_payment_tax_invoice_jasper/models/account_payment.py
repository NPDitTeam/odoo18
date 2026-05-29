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
    'pfb_npd_payment_tax_invoice_jasper/static/img/Signature.png'
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


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    jasper_baht_text = fields.Char(
        string='Baht Text',
        compute='_compute_jasper_baht_text',
    )
    jasper_date_thai = fields.Char(
        string='Date (Thai short)',
        compute='_compute_jasper_date_thai',
    )
    jasper_partner_full_address = fields.Char(
        string='Partner Full Address',
        compute='_compute_jasper_partner_full_address',
    )
    jasper_partner_vat_display = fields.Char(
        string='Partner VAT Display',
        compute='_compute_jasper_partner_vat_display',
    )
    jasper_company_address = fields.Char(
        string='Company Address',
        compute='_compute_jasper_company_address',
    )
    jasper_company_name_display = fields.Char(
        string='Company Name Display',
        compute='_compute_jasper_company_name_display',
    )
    jasper_branch_address = fields.Char(
        string='Branch Address',
        compute='_compute_jasper_branch_address',
    )
    jasper_amount_untaxed = fields.Float(
        string='Amount Untaxed',
        compute='_compute_jasper_amount_values',
    )
    jasper_amount_tax = fields.Float(
        string='Amount Tax',
        compute='_compute_jasper_amount_values',
    )
    jasper_signature = fields.Binary(
        string='Signature Image',
        compute='_compute_jasper_signature',
    )

    @api.depends('amount')
    def _compute_jasper_baht_text(self):
        try:
            from bahttext import bahttext
        except ImportError:
            bahttext = None
        for rec in self:
            amount = rec.amount or 0.0
            if bahttext:
                rec.jasper_baht_text = bahttext(amount)
            else:
                rec.jasper_baht_text = '{:,.2f}'.format(amount)

    @api.depends('date')
    def _compute_jasper_date_thai(self):
        for rec in self:
            rec.jasper_date_thai = _format_thai_date_short(rec.date)

    @api.depends(
        'partner_id.street', 'partner_id.street2',
        'partner_id.city', 'partner_id.state_id',
        'partner_id.zip',
    )
    def _compute_jasper_partner_full_address(self):
        for rec in self:
            p = rec.partner_id
            state_name = p.state_id.name if p.state_id else ''
            rec.jasper_partner_full_address = _join_address(
                p.street, p.street2, p.city, state_name, p.zip,
            )

    @api.depends('partner_id.vat')
    def _compute_jasper_partner_vat_display(self):
        for rec in self:
            vat = rec.partner_id.vat or ''
            rec.jasper_partner_vat_display = (
                '{} (สำนักงานใหญ่)'.format(vat) if vat else ''
            )

    @api.depends(
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id',
        'company_id.zip',
    )
    def _compute_jasper_company_address(self):
        for rec in self:
            c = rec.company_id
            state_name = c.state_id.name if c.state_id else ''
            rec.jasper_company_address = _join_address(
                c.street, c.street2, c.city, state_name, c.zip,
            )

    @api.depends('company_id.name')
    def _compute_jasper_company_name_display(self):
        for rec in self:
            name = rec.company_id.name or ''
            rec.jasper_company_name_display = (
                '{} (สำนักงานใหญ่)'.format(name) if name else ''
            )

    @api.depends(
        'branch_id', 'branch_id.street', 'branch_id.street2',
        'branch_id.city', 'branch_id.state_id', 'branch_id.zip',
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id', 'company_id.zip',
    )
    def _compute_jasper_branch_address(self):
        for rec in self:
            branch = rec.branch_id
            if branch:
                state_name = branch.state_id.name if branch.state_id else ''
                addr = _join_address(
                    branch.street, branch.street2, branch.city,
                    state_name, branch.zip,
                )
                if addr:
                    rec.jasper_branch_address = addr
                    continue
            c = rec.company_id
            state_name = c.state_id.name if c.state_id else ''
            rec.jasper_branch_address = _join_address(
                c.street, c.street2, c.city, state_name, c.zip,
            )

    @api.depends('amount')
    def _compute_jasper_amount_values(self):
        for rec in self:
            amt = rec.amount or 0.0
            untaxed = amt / 1.07
            rec.jasper_amount_untaxed = untaxed
            rec.jasper_amount_tax = amt - untaxed

    def _compute_jasper_signature(self):
        signature_b64 = False
        try:
            with tools.file_open(SIGNATURE_RESOURCE_PATH, 'rb') as f:
                signature_b64 = base64.b64encode(f.read())
        except Exception as e:
            _logger.warning('Could not load signature image: %s', e)
        for rec in self:
            rec.jasper_signature = signature_b64

    def get_baht_text_tax_invoice(self):
        self.ensure_one()
        try:
            from bahttext import bahttext
        except ImportError:
            return '{:,.2f}'.format(self.amount or 0.0)
        return bahttext(self.amount or 0.0)
