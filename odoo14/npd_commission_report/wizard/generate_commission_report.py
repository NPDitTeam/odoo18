# -*- coding: utf-8 -*-
"""ตัวช่วยสั่งสร้างรายงานค่าคอมของงวดที่เลือก"""
from odoo import _, api, fields, models

from ..models.commission_report import MONTH_SELECTION


class GenerateCommissionReport(models.TransientModel):
    _name = 'generate.commission.report'
    _description = 'สร้างรายงานค่าคอมมิชชั่นสาขา'

    @api.model
    def _year_selection(self):
        current = fields.Date.today().year
        return [(str(y), str(y)) for y in range(current - 5, current + 2)]

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company,
        help='คิดยอดเฉพาะเอกสารของบริษัทนี้ — ระบบรวมหลายบริษัทไว้ฐานเดียว '
             'ถ้าไม่แยกยอดจะปนกัน')
    month = fields.Selection(
        MONTH_SELECTION, string='เดือน', required=True,
        default=lambda self: str(fields.Date.today().month))
    year = fields.Selection(
        selection='_year_selection', string='ปี', required=True,
        default=lambda self: str(fields.Date.today().year))
    branch_ids = fields.Many2many(
        'res.branch', string='เฉพาะสาขา',
        help='เว้นว่าง = ทุกสาขาของบริษัทนี้')

    also_sales = fields.Boolean(
        string='สร้างรายงานค่าคอม Sales ด้วย', default=True,
        help='คิดยอดรายเซลล์ควบคู่กับรายสาขา ใช้ข้อมูลชุดเดียวกัน '
             'สร้างพร้อมกันจะได้ไม่หลุดงวดใดงวดหนึ่ง')

    def action_generate(self):
        self.ensure_one()
        branches = self.branch_ids or None
        records = self.env['npd.commission.report'].generate(
            self.month, self.year, company=self.company_id, branches=branches)
        if self.also_sales:
            self.env['npd.commission.report.sales'].generate(
                self.month, self.year, company=self.company_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('รายงานค่าคอมมิชชั่นสาขา'),
            'res_model': 'npd.commission.report',
            'view_mode': 'list,form',
            'domain': [('id', 'in', records.ids)],
            'target': 'current',
        }
