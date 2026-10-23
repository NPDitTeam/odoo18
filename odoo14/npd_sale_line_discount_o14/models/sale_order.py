# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_draft(self):
        # ยกเลิกแล้วตั้งกลับเป็นใบเสนอราคา = ทำใหม่ การอนุมัติเดิม (ส่วนลด/ค่าประกัน) ต้องเริ่มใหม่ด้วย
        # ไม่งั้นแก้ส่วนลดเพิ่มแล้วยังขึ้น "อนุมัติแล้ว" Convert ได้เลย (SO-261023-0026, 23 ต.ค. 2569)
        res = super().action_draft()
        if 'state_sale' in self._fields:
            self.filtered(lambda o: o.state == 'draft' and o.state_sale != 'draft').write({'state_sale': 'draft'})
        return res

    def _show_cancel_wizard(self):
        # กดยกเลิกแล้วยกเลิกเลย ไม่เปิดหน้าส่งอีเมลแจ้งลูกค้า (ผู้ใช้สั่ง 23 ต.ค. 2569)
        return False

    # แทนของ pfb_npd_all_customs: รวมส่วนลดเป็นบาท (o14 เอาตัวเลขที่กรอกมาบวกตรง ๆ
    # เลือก Percentage 20 + 20 เลยขึ้น 40 แทน 44 บาท) และคิดใหม่เมื่อยอด/ประเภทการลดราคาเปลี่ยน
    @api.depends('order_line.discount_type_selection', 'order_line.discount_amount',
                 'order_line.discount_method', 'order_line.price_unit',
                 'order_line.product_uom_qty', 'order_line.tax_id')
    def _compute_total_rental_discount(self):
        for order in self:
            rental_discount = product_discount = 0.0
            for line in order.order_line:
                baht = line._npd_discount_baht()
                if line.discount_type_selection == 'rental':
                    rental_discount += baht
                elif not line.discount_type_selection or line.discount_type_selection == 'product':
                    product_discount += baht
            order.total_rental_discount = rental_discount
            order.discount_amt_line = product_discount
