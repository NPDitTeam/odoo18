# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    discount_method = fields.Selection(
        [('fix', 'Fixed'), ('per', 'Percentage')], string='ประเภทการลดราคา')
    # ชื่อเดียวกับ bi_sale_purchase_discount_with_tax ของ o14 — sale_isolated_quotation ใช้เป็นฐานเกณฑ์ 50%
    # o18 ส่วนลดไม่หักใน price_subtotal จึงเท่ากับยอดรายการ (o14 ต่างกันแค่การปัดเศษ)
    price_subtotal_without_discount = fields.Monetary(
        string='ยอดหลังหักส่วนลด', compute='_compute_price_subtotal_without_discount')
    commitment_date = fields.Datetime(
        related='order_id.commitment_date', string='วันที่จัดส่งสินค้า')

    @api.depends('price_subtotal')
    def _compute_price_subtotal_without_discount(self):
        for line in self:
            line.price_subtotal_without_discount = line.price_subtotal

    @api.onchange('discount_amount', 'discount_type_selection', 'discount_method')
    def _onchange_npd_discount_limit(self):
        # แทน _onchange_discount_amount ของ pfb_npd_all_customs (ไม่มี decorator + ข้อความติด %%)
        for line in self:
            if line.discount_amount and line.discount_type_selection == 'product':
                max_discount = line.price_subtotal_without_discount * 0.5
                if max_discount and line.discount_amount > max_discount:
                    return {'warning': {
                        'title': _('ส่วนลดเกินเกณฑ์'),
                        'message': _('ส่วนลดเกิน 50%% ของยอดรายการ (สูงสุด %s)\n'
                                     'ต้องกด "Send for Approval" ให้ผู้อนุมัติก่อน Convert to Order')
                        % '{:,.2f}'.format(max_discount),
                    }}
