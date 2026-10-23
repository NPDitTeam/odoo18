# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools import html2plaintext, is_html_empty, plaintext2html


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # เงื่อนไขและข้อกำหนดแบบข้อความธรรมดา ไม่มีแถบเครื่องมือ (ผู้ใช้สั่ง 23 ต.ค. 2569 เหมือนใบลดหนี้)
    # ข้อมูลยังเก็บใน note (Html) เดิม ใบแจ้งหนี้/รายงานที่อ่าน note จึงใช้ได้เหมือนเดิม
    npd_note_text = fields.Text(
        string='เงื่อนไขและข้อกำหนด',
        compute='_compute_npd_note_text', inverse='_inverse_npd_note_text')

    def _compute_npd_note_text(self):
        for order in self:
            order.npd_note_text = '' if is_html_empty(order.note) else html2plaintext(order.note)

    def _inverse_npd_note_text(self):
        for order in self:
            text = (order.npd_note_text or '').strip()
            order.note = plaintext2html(text) if text else False

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
