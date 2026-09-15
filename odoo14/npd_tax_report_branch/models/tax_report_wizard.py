# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .tax_report import REPORT_TAX_TYPES, branch_filter_cell


class TaxReportWizard(models.TransientModel):
    _inherit = 'tax.report.wizard'

    report_tax_type = fields.Selection(
        REPORT_TAX_TYPES,
        string='ประเภทภาษี',
        required=True,
    )
    branch_all = fields.Boolean(string='ทุกสาขา', default=True)
    # แยก 2 ฟิลด์เพื่อให้ป้ายชื่อตรงกับสิ่งที่ใช้กรอง ใช้จริงทีละตัวตามประเภทภาษี
    filter_branch_id = fields.Many2one(
        'res.branch',
        string='สาขา',
        domain="['|', ('company_id', '=', company_id), ('company_ids', 'in', [company_id])]",
        help='ภาษีขาย: กรองตาม Branch ของเอกสาร',
    )
    filter_head_office_branch_id = fields.Many2one(
        'res.branch',
        string='สาขาสำนักงานใหญ่',
        domain="['|', ('company_id', '=', company_id), ('company_ids', 'in', [company_id])]",
        help='ภาษีซื้อ: กรองตามฟิลด์ "สาขาสำนักงานใหญ่" ของ Avance Clear / การรับ / บิลผู้ขาย',
    )

    @api.onchange('tax_group_id', 'report_tax_type')
    def _set_tex_id(self):
        super()._set_tex_id()
        for rec in self:
            rec.tax_id = rec.tax_id.filtered(
                lambda tax: tax.type_tax_use == rec.report_tax_type)

    @api.onchange('report_tax_type')
    def _onchange_report_tax_type_branch(self):
        self.filter_branch_id = False
        self.filter_head_office_branch_id = False

    def _get_selected_branch(self):
        self.ensure_one()
        if self.report_tax_type == 'purchase':
            return self.filter_head_office_branch_id
        return self.filter_branch_id

    def _check_branch_filter(self):
        self.ensure_one()
        wrong = self.tax_id.filtered(lambda tax: tax.type_tax_use != self.report_tax_type)
        if wrong:
            raise UserError(_(
                'ภาษีซื้อกับภาษีขายเลือกรวมกันไม่ได้\n'
                'ภาษีต่อไปนี้ไม่ใช่ %s: %s'
            ) % (dict(REPORT_TAX_TYPES)[self.report_tax_type], ', '.join(wrong.mapped('name'))))
        if not self.branch_all and not self._get_selected_branch():
            raise UserError(_('กรุณาเลือกสาขา หรือติ๊ก "ทุกสาขา"'))

    def _prepare_tax_report(self):
        # View / Export PDF / Export Excel ผ่านเมธอดนี้ทั้งหมด
        self._check_branch_filter()
        values = super()._prepare_tax_report()
        values.update({
            'report_tax_type': self.report_tax_type,
            'branch_all': self.branch_all,
            'filter_branch_id': False if self.branch_all else self._get_selected_branch().id,
        })
        return values

    def _get_extra_filter_cells(self):
        return super()._get_extra_filter_cells() + [
            branch_filter_cell(self.report_tax_type, self.branch_all, self._get_selected_branch()),
        ]
