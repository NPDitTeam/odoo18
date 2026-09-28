# -*- coding: utf-8 -*-
"""สรุปผลตรวจนับสินค้าที่ระดับใบจอง

แอปฝั่งคนขับต้องรู้ด้วยคำตอบเดียวว่า "ตรวจครบหรือยัง" เพื่อปลดล็อกปุ่มกล้อง
ถ้าให้แอปไปไล่นับบรรทัดเอง ตรรกะจะอยู่สองที่แล้วเพี้ยนกันเมื่อแก้ข้างเดียว
"""
from odoo import _, api, fields, models

CHECK_SUMMARY = [
    ('no_line', 'ไม่มีรายการสินค้า'),
    ('pending', 'ยังไม่ได้ตรวจ'),
    ('partial', 'ตรวจบางรายการ'),
    ('done', 'ตรวจครบแล้ว'),
]


class VehicleBookingProductCheck(models.Model):
    _inherit = 'vehicle.booking'

    product_check_state = fields.Selection(
        CHECK_SUMMARY, string='สถานะตรวจนับสินค้า',
        compute='_compute_product_check', store=True, index=True)
    product_check_done = fields.Integer(
        string='ตรวจแล้ว (รายการ)', compute='_compute_product_check', store=True)
    product_check_total = fields.Integer(
        string='ทั้งหมด (รายการ)', compute='_compute_product_check', store=True)
    product_check_mismatch = fields.Integer(
        string='ไม่ตรงจำนวน (รายการ)', compute='_compute_product_check', store=True,
        help='จำนวนรายการที่คนขับนับแล้วไม่ตรงกับที่สั่ง')
    can_take_photo = fields.Boolean(
        string='ถ่ายรูปได้', compute='_compute_product_check', store=True,
        help='ต้องตรวจนับครบทุกรายการก่อน ไม่ว่าผลจะตรงหรือไม่ตรง '
             'เพราะรูปคือหลักฐานของของที่ขาดด้วย')

    # order_line_ids เป็นฟิลด์คำนวณที่ไม่เก็บค่า อ้างมันตรง ๆ แล้ว Odoo
    # หาไม่เจอว่าต้องคำนวณใบไหนใหม่เมื่อบรรทัดเปลี่ยน (ขึ้นคำเตือน
    # "should be searchable") ต้องอ้างเส้นทางจริงที่เก็บในฐานแทน
    @api.depends('transport_order_id',
                 'transport_order_id.order_line_ids',
                 'transport_order_id.order_line_ids.check_state')
    def _compute_product_check(self):
        for booking in self:
            lines = booking.transport_order_id.order_line_ids
            total = len(lines)
            checked = lines.filtered(lambda l: l.check_state != 'pending')
            mismatch = lines.filtered(lambda l: l.check_state == 'incorrect')
            booking.product_check_total = total
            booking.product_check_done = len(checked)
            booking.product_check_mismatch = len(mismatch)
            if not total:
                # ไม่มีรายการสินค้าให้ตรวจ ก็ไม่ควรไปขวางไม่ให้ถ่ายรูป
                booking.product_check_state = 'no_line'
                booking.can_take_photo = True
            elif not checked:
                booking.product_check_state = 'pending'
                booking.can_take_photo = False
            elif len(checked) < total:
                booking.product_check_state = 'partial'
                booking.can_take_photo = False
            else:
                booking.product_check_state = 'done'
                booking.can_take_photo = True
