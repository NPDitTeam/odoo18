# -*- coding: utf-8 -*-
from odoo import api, fields, models


class NpdPayrollAccountReverseWizard(models.TransientModel):
    _name = 'npd.payroll.account.reverse.wizard'
    _description = 'กลับรายการบัญชีเงินเดือน'

    link_id = fields.Many2one(
        'npd.payroll.account.move', string='รายการที่จะกลับ', required=True,
        readonly=True, ondelete='cascade')
    date = fields.Date(
        string='วันที่กลับรายการ', required=True,
        help='ถ้างวดของวันที่ลงบัญชีเดิมถูกล็อกแล้ว ให้เลือกวันที่ในงวดที่ยังเปิดอยู่')
    reason = fields.Char(string='เหตุผล')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        link_id = res.get('link_id') or self.env.context.get('default_link_id')
        if link_id and 'date' in fields_list and not res.get('date'):
            link = self.env['npd.payroll.account.move'].sudo().browse(link_id)
            res['date'] = link.date or fields.Date.context_today(self)
        return res

    def action_reverse(self):
        self.ensure_one()
        self.link_id._npd_reverse(self.date, self.reason)
        return {'type': 'ir.actions.act_window_close'}
