# -*- coding: utf-8 -*-
"""แก้ Sales ที่ติดต่อ / วันที่กำหนดจ่าย ของใบสำคัญที่ลงบัญชีแล้ว

พอร์ตจาก Odoo 14 (account_advance_sales_contact) — o14 เขียนด้วย SQL แล้ว commit เอง
ที่นี่ใช้ write() ปกติ เพราะ account.voucher.line ยอมให้แก้สองฟิลด์นี้หลังลงบัญชีอยู่แล้ว
"""
from odoo import api, fields, models

from ..models.account_voucher import SALES_USER_DOMAIN


class WizardEditSalesContact(models.TransientModel):
    _name = 'wizard.edit.sales.contact'
    _description = 'แก้ไข Sales ที่ติดต่อและวันที่กำหนดจ่าย'

    voucher_id = fields.Many2one('account.voucher', string='Voucher', required=True)
    line_ids = fields.One2many('wizard.edit.sales.contact.line', 'wizard_id', string='รายการ')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        voucher = self.env['account.voucher'].browse(self.env.context.get('default_voucher_id'))
        if voucher.exists():
            res['line_ids'] = [(0, 0, {
                'voucher_line_id': line.id,
                'product_id': line.product_id.id,
                'name': line.name,
                'sales_contact_id': line.sales_contact_id.id,
                'payment_date': line.payment_date,
            }) for line in voucher.line_ids]
        return res

    def action_confirm(self):
        for wiz_line in self.line_ids.filtered('voucher_line_id'):
            line = wiz_line.voucher_line_id
            vals = {}
            if line.sales_contact_id != wiz_line.sales_contact_id:
                vals['sales_contact_id'] = wiz_line.sales_contact_id.id
            if line.payment_date != wiz_line.payment_date:
                vals['payment_date'] = wiz_line.payment_date
            if vals:
                line.write(vals)
        return {'type': 'ir.actions.act_window_close'}


class WizardEditSalesContactLine(models.TransientModel):
    _name = 'wizard.edit.sales.contact.line'
    _description = 'แก้ไข Sales ที่ติดต่อ (รายการ)'

    wizard_id = fields.Many2one('wizard.edit.sales.contact', required=True, ondelete='cascade')
    voucher_line_id = fields.Many2one('account.voucher.line', string='รายการใบสำคัญ')
    product_id = fields.Many2one('product.product', string='สินค้า', readonly=True)
    name = fields.Char(string='รายละเอียด', readonly=True)
    sales_contact_id = fields.Many2one('res.users', string='Sales ที่ติดต่อ',
                                       domain=SALES_USER_DOMAIN)
    payment_date = fields.Date(string='วันที่กำหนดจ่าย')
