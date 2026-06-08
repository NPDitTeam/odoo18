import logging
import re

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

THAI_MONTHS = {
    1: 'มกราคม', 2: 'กุมภาพันธ์', 3: 'มีนาคม', 4: 'เมษายน',
    5: 'พฤษภาคม', 6: 'มิถุนายน', 7: 'กรกฎาคม', 8: 'สิงหาคม',
    9: 'กันยายน', 10: 'ตุลาคม', 11: 'พฤศจิกายน', 12: 'ธันวาคม',
}


def _join_address(*parts):
    return ' '.join(p for p in parts if p)


def _strip_html(html):
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
            .replace('&lt;', '<').replace('&gt;', '>'))
    return re.sub(r'\s+', ' ', text).strip()


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ===== Header: company (โลโก้/ชื่อ/ที่อยู่ ดึงตามบริษัทที่เลือก = company_id) =====
    jasper_jv_company_name = fields.Char(
        compute='_compute_jasper_jv_company',
    )
    jasper_jv_company_address = fields.Char(
        compute='_compute_jasper_jv_company',
    )

    # ===== Document info =====
    jasper_jv_partner_name = fields.Char(
        compute='_compute_jasper_jv_partner_name',
    )
    jasper_jv_date_thai = fields.Char(
        compute='_compute_jasper_jv_date_thai',
    )
    jasper_jv_narration_clean = fields.Char(
        compute='_compute_jasper_jv_narration_clean',
    )

    # ===== Accounting totals =====
    jasper_jv_sum_debit = fields.Float(
        compute='_compute_jasper_jv_sums',
    )
    jasper_jv_sum_credit = fields.Float(
        compute='_compute_jasper_jv_sums',
    )

    @api.depends(
        'company_id.name',
        'branch_id', 'branch_id.street', 'branch_id.street2',
        'branch_id.city', 'branch_id.state_id', 'branch_id.zip',
        'company_id.street', 'company_id.street2',
        'company_id.city', 'company_id.state_id', 'company_id.zip',
    )
    def _compute_jasper_jv_company(self):
        for rec in self:
            rec.jasper_jv_company_name = rec.company_id.name or ''
            # ที่อยู่: ดึงจากสาขา (branch_id) ก่อน ถ้าไม่มีค่อย fallback ไปบริษัท
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
            rec.jasper_jv_company_address = addr

    @api.depends('partner_id.name', 'line_ids.partner_id')
    def _compute_jasper_jv_partner_name(self):
        for rec in self:
            name = rec.partner_id.name or ''
            if not name:
                for line in rec.line_ids:
                    if line.partner_id:
                        name = line.partner_id.name
                        break
            rec.jasper_jv_partner_name = name

    @api.depends('date')
    def _compute_jasper_jv_date_thai(self):
        for rec in self:
            dt = rec.date
            if dt:
                rec.jasper_jv_date_thai = '{}/{}/{}'.format(
                    dt.strftime('%d'), dt.strftime('%m'), dt.year + 543
                )
            else:
                rec.jasper_jv_date_thai = ''

    @api.depends('narration')
    def _compute_jasper_jv_narration_clean(self):
        for rec in self:
            rec.jasper_jv_narration_clean = _strip_html(rec.narration or '')

    @api.depends('line_ids.debit', 'line_ids.credit')
    def _compute_jasper_jv_sums(self):
        for rec in self:
            rec.jasper_jv_sum_debit = sum(l.debit for l in rec.line_ids)
            rec.jasper_jv_sum_credit = sum(l.credit for l in rec.line_ids)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    jasper_jv_account_code = fields.Char(
        compute='_compute_jasper_jv_line_fields',
    )
    jasper_jv_account_name = fields.Char(
        compute='_compute_jasper_jv_line_fields',
    )
    jasper_jv_analytic = fields.Char(
        compute='_compute_jasper_jv_line_fields',
    )

    @api.depends('account_id.code', 'account_id.name', 'analytic_distribution')
    def _compute_jasper_jv_line_fields(self):
        for line in self:
            line.jasper_jv_account_code = line.account_id.code or ''
            line.jasper_jv_account_name = line.account_id.name or ''
            # งบโครงการ: ดึงชื่อ analytic จาก analytic_distribution (ถ้ามี)
            names = []
            dist = line.analytic_distribution or {}
            if dist:
                ids = []
                for key in dist.keys():
                    for part in str(key).split(','):
                        if part.isdigit():
                            ids.append(int(part))
                if ids:
                    accounts = line.env['account.analytic.account'].browse(ids)
                    names = [a.name for a in accounts if a.exists() and a.name]
            line.jasper_jv_analytic = ', '.join(names)
