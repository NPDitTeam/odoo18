# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ฟิลด์สำหรับเช็คว่าผู้ใช้สามารถแก้ไขวันที่ได้หรือไม่
    can_edit_invoice_date = fields.Boolean(
        string='สามารถแก้ไขวันที่ Invoice',
        compute='_compute_can_edit_invoice_date',
        store=False
    )

    # ฟิลด์สำหรับเก็บว่ามาจากใบเสนอราคาแบบจองหรือไม่
    is_from_reservation = fields.Boolean(
        string='มาจากใบเสนอราคาแบบจอง',
        compute='_compute_is_from_reservation',
        store=False
    )

    @api.depends('invoice_origin', 'invoice_line_ids.sale_line_ids')
    def _compute_is_from_reservation(self):
        """คำนวณว่า Invoice มาจากใบเสนอราคาแบบจองหรือไม่

        o14 ค้นใบสั่งขายจากชื่อใน invoice_origin อย่างเดียว ซึ่งไม่เจอเมื่อรวมหลายใบสั่ง
        ("SO1, SO2") o18 จึงดูจากบรรทัดที่ผูกกับใบสั่งขายก่อน แล้วค่อยค้นตามชื่อ"""
        for move in self:
            orders = move.invoice_line_ids.sale_line_ids.order_id
            if not orders and move.invoice_origin:
                names = [n.strip() for n in move.invoice_origin.split(',') if n.strip()]
                orders = self.env['sale.order'].search([('name', 'in', names)])
            move.is_from_reservation = any(orders.mapped('is_reservation_quotation'))

    @api.depends('invoice_origin')
    @api.depends_context('uid')
    def _compute_can_edit_invoice_date(self):
        """คำนวณว่าผู้ใช้ปัจจุบันสามารถแก้ไขวันที่ได้หรือไม่
        ผู้ใช้ที่ได้รับอนุญาต หรือเป็นเอกสารที่สร้างเอง (ไม่มี invoice_origin) แก้ได้"""
        allowed = self.env.user.allow_edit_invoice_date
        for move in self:
            move.can_edit_invoice_date = allowed or not move.invoice_origin
