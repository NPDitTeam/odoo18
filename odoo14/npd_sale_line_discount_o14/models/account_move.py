# -*- coding: utf-8 -*-
"""ใบแจ้งหนี้ที่สร้างจากใบสั่งขาย แสดงส่วนลดแบบ o14 (ผู้ใช้สั่ง 23 ต.ค. 2569)

ยอดหักจริงมาจากช่อง "ลด%" มาตรฐานอยู่แล้ว ส่วนนี้แค่ส่ง ประเภทการลดราคา/ยอดส่วนลด ตามมาให้เห็น
และรวม - Line Discount / - Rental Discount เป็นบาท (ของเดิมบวกตัวเลขที่กรอกตรง ๆ เลือก Percentage แล้วผิด)
"""
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.depends('invoice_line_ids.discount_type_selection', 'invoice_line_ids.discount_amount',
                 'invoice_line_ids.discount_method', 'invoice_line_ids.price_unit',
                 'invoice_line_ids.quantity', 'invoice_line_ids.tax_ids')
    def _compute_total_rental_discount(self):
        for move in self:
            rental_discount = product_discount = 0.0
            for line in move.invoice_line_ids:
                baht = line._npd_discount_baht()
                if line.discount_type_selection == 'rental':
                    rental_discount += baht
                elif not line.discount_type_selection or line.discount_type_selection == 'product':
                    product_discount += baht
            move.total_rental_discount = rental_discount
            move.discount_amt_line = product_discount


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    discount_method = fields.Selection(
        [('fix', 'Fixed'), ('per', 'Percentage')], string='ประเภทการลดราคา')
    discount_amount = fields.Float(string='ยอดส่วนลด')

    def _npd_discount_baht(self):
        self.ensure_one()
        if not self.discount_amount:
            return 0.0
        if self.discount_method != 'per':
            return self.discount_amount
        gross = self.tax_ids.compute_all(
            self.price_unit, self.move_id.currency_id, self.quantity,
            product=self.product_id, partner=self.move_id.partner_id)['total_excluded']
        return gross * self.discount_amount / 100.0


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        if self.discount_method and self.discount_amount:
            res.update({'discount_method': self.discount_method, 'discount_amount': self.discount_amount})
        return res
