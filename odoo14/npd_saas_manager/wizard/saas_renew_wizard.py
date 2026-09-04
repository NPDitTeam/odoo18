# -*- coding: utf-8 -*-
"""ต่ออายุสัญญาเช่าระบบ"""
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import UserError


class SaasRenewWizard(models.TransientModel):
    _name = 'saas.renew.wizard'
    _description = 'ต่ออายุสัญญาเช่าระบบ'

    tenant_id = fields.Many2one('hrms.tenant', string='องค์กร', required=True)
    current_expire = fields.Date(
        related='tenant_id.expire_date', string='หมดอายุปัจจุบัน', readonly=True)
    months = fields.Integer(string='ต่ออายุ (เดือน)', default=12, required=True)
    new_expire = fields.Date(
        string='หมดอายุใหม่', compute='_compute_new_expire', store=False)
    amount = fields.Monetary(string='ค่าบริการ', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    note = fields.Char(string='หมายเหตุ')

    @api.depends('tenant_id', 'months')
    def _compute_new_expire(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.tenant_id or rec.months <= 0:
                rec.new_expire = False
                continue
            # ต่อจากวันหมดอายุเดิมถ้ายังไม่หมด เพื่อไม่ให้ลูกค้าเสียวันที่จ่ายไปแล้ว
            # ถ้าหมดไปแล้วให้เริ่มนับจากวันนี้ ไม่ย้อนหลังให้ฟรี
            base = rec.tenant_id.expire_date or today
            if base < today:
                base = today
            rec.new_expire = base + relativedelta(months=rec.months)

    def action_confirm(self):
        self.ensure_one()
        if self.months <= 0:
            raise UserError('จำนวนเดือนต้องมากกว่า 0')
        tenant = self.tenant_id
        previous = tenant.expire_date

        self.env['saas.renewal'].create({
            'tenant_id': tenant.id,
            'months': self.months,
            'previous_expire': previous,
            'new_expire': self.new_expire,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'note': self.note,
        })

        tenant.write({
            'expire_date': self.new_expire,
            'state': 'active',
            'start_date': tenant.start_date or fields.Date.context_today(self),
        })
        tenant.push_license()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'ต่ออายุเรียบร้อย',
                'message': '%s ใช้งานได้ถึง %s' % (tenant.name, self.new_expire),
                'type': 'success',
            },
        }
