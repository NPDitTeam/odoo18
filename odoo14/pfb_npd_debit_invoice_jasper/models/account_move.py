import logging
import re

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


def _join_address(*parts):
    return ' '.join(p for p in parts if p)


def _strip_html(html):
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
            .replace('&lt;', '<').replace('&gt;', '>'))
    return re.sub(r'\s+', ' ', text).strip()


def _fmt_date(dt):
    return dt.strftime('%d/%m/%Y') if dt else ''


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ===== Header: company (logo/ชื่อ/ที่อยู่ แบบเดียวกับใบสำคัญจ่าย: branch ก่อน fallback company) =====
    jasper_dn_company_name = fields.Char(
        compute='_compute_jasper_dn_company',
    )
    jasper_dn_company_address = fields.Char(
        compute='_compute_jasper_dn_company',
    )

    # ===== Customer / shipping =====
    jasper_dn_partner_address = fields.Char(
        compute='_compute_jasper_dn_partner_address',
    )
    jasper_dn_partner_vat_branch = fields.Char(
        compute='_compute_jasper_dn_partner_vat_branch',
    )
    jasper_dn_shipping_name = fields.Char(
        compute='_compute_jasper_dn_shipping',
    )
    jasper_dn_shipping_address = fields.Char(
        compute='_compute_jasper_dn_shipping',
    )

    # ===== Dates / terms =====
    jasper_dn_invoice_date_str = fields.Char(
        compute='_compute_jasper_dn_dates',
    )
    jasper_dn_date_due_str = fields.Char(
        compute='_compute_jasper_dn_dates',
    )
    jasper_dn_payment_term = fields.Char(
        compute='_compute_jasper_dn_payment_term',
    )

    # ===== Baht text / narration =====
    jasper_dn_baht_text = fields.Char(
        compute='_compute_jasper_dn_baht_text',
    )
    jasper_dn_narration_clean = fields.Char(
        compute='_compute_jasper_dn_narration_clean',
    )

    @api.depends(
        'company_id.name',
        'branch_id', 'branch_id.street', 'branch_id.street2',
        'branch_id.city', 'branch_id.state_id', 'branch_id.zip',
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id', 'company_id.zip',
    )
    def _compute_jasper_dn_company(self):
        for rec in self:
            rec.jasper_dn_company_name = rec.company_id.name or ''
            branch = rec.branch_id
            addr = ''
            if branch:
                state_name = branch.state_id.name if branch.state_id else ''
                addr = _join_address(
                    branch.street, branch.street2, branch.city,
                    state_name, branch.zip,
                )
            if not addr:
                c = rec.company_id
                state_name = c.state_id.name if c.state_id else ''
                addr = _join_address(
                    c.street, c.street2, c.city, state_name, c.zip,
                )
            rec.jasper_dn_company_address = addr

    @api.depends(
        'partner_id.street', 'partner_id.street2',
        'partner_id.city', 'partner_id.state_id', 'partner_id.zip',
    )
    def _compute_jasper_dn_partner_address(self):
        for rec in self:
            p = rec.partner_id
            state_name = p.state_id.name if p.state_id else ''
            rec.jasper_dn_partner_address = _join_address(
                p.street, p.street2, p.city, state_name, p.zip,
            )

    @api.depends('partner_id.vat', 'partner_id.branch')
    def _compute_jasper_dn_partner_vat_branch(self):
        for rec in self:
            p = rec.partner_id
            vat = p.vat or ''
            branch = p.branch or ''
            if branch == '00000':
                suffix = '(สำนักงานใหญ่)'
            elif branch:
                suffix = 'สาขาที่ {}'.format(branch)
            else:
                suffix = ''
            rec.jasper_dn_partner_vat_branch = '{}  {}'.format(vat, suffix).strip()

    @api.depends(
        'partner_shipping_id.name', 'partner_shipping_id.street',
        'partner_shipping_id.street2', 'partner_shipping_id.city',
        'partner_shipping_id.state_id', 'partner_shipping_id.zip',
    )
    def _compute_jasper_dn_shipping(self):
        for rec in self:
            p = rec.partner_shipping_id
            state_name = p.state_id.name if p.state_id else ''
            rec.jasper_dn_shipping_name = p.name or ''
            rec.jasper_dn_shipping_address = _join_address(
                p.street, p.street2, p.city, state_name, p.zip,
            )

    @api.depends('invoice_date', 'invoice_date_due')
    def _compute_jasper_dn_dates(self):
        for rec in self:
            rec.jasper_dn_invoice_date_str = _fmt_date(rec.invoice_date)
            rec.jasper_dn_date_due_str = _fmt_date(rec.invoice_date_due)

    @api.depends('invoice_payment_term_id.name')
    def _compute_jasper_dn_payment_term(self):
        for rec in self:
            rec.jasper_dn_payment_term = rec.invoice_payment_term_id.name or ''

    @api.depends('amount_total')
    def _compute_jasper_dn_baht_text(self):
        try:
            from bahttext import bahttext
        except ImportError:
            bahttext = None
        for rec in self:
            amount = rec.amount_total or 0.0
            if bahttext:
                rec.jasper_dn_baht_text = bahttext(amount)
            else:
                rec.jasper_dn_baht_text = '{:,.2f}'.format(amount)

    @api.depends('narration')
    def _compute_jasper_dn_narration_clean(self):
        for rec in self:
            rec.jasper_dn_narration_clean = _strip_html(rec.narration or '')


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    jasper_dn_product_code = fields.Char(
        compute='_compute_jasper_dn_line_fields',
    )
    jasper_dn_uom_name = fields.Char(
        compute='_compute_jasper_dn_line_fields',
    )
    # ชื่อสินค้าโดยตัด "[รหัส]" นำหน้าออก (เอาแค่ชื่อ)
    jasper_dn_line_desc = fields.Char(
        compute='_compute_jasper_dn_line_fields',
    )

    @api.depends('product_id.default_code', 'product_uom_id.name', 'name')
    def _compute_jasper_dn_line_fields(self):
        for line in self:
            line.jasper_dn_product_code = line.product_id.default_code or ''
            line.jasper_dn_uom_name = line.product_uom_id.name or ''
            line.jasper_dn_line_desc = re.sub(
                r'^\s*\[[^\]]*\]\s*', '', line.name or '')
