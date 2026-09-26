# -*- coding: utf-8 -*-
"""ธงบอกว่าใบนี้ยกมาจาก Odoo 14 ไม่ได้สร้างบนฝั่ง 18"""
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    o14_imported = fields.Boolean(
        string='ยกมาจาก Odoo 14', readonly=True, copy=False, index=True,
        help='ใบที่ยกข้อมูลมาตอนย้ายระบบ ไม่ใช่ใบที่สร้างบนฝั่ง 18 '
             'ใช้แยกตอนตรวจยอดและตอนคิดค่าคอม')
    o14_source_db = fields.Char(
        string='ฐานต้นทาง', readonly=True, copy=False,
        help='ชื่อฐานข้อมูลฝั่ง 14 ที่ใบนี้ถูกยกมา')
    o14_order_name = fields.Char(
        string='เลขใบฝั่ง 14', readonly=True, copy=False, index=True)
    o14_order_id = fields.Integer(
        string='id ฝั่ง 14', readonly=True, copy=False)
