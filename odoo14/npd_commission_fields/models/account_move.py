# -*- coding: utf-8 -*-
"""เซลล์ผู้ติดต่อและประเภทสินค้าบนใบแจ้งหนี้

``contact_type`` มีอยู่แล้วในระบบ (จาก pfb_npd_all_customs) ไฟล์นี้จึงเพิ่ม
เฉพาะสองฟิลด์ที่ยังขาด และรายงานค่าคอมต้องใช้
"""
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    sales_contact_id = fields.Many2one(
        'res.users', string='Sales ที่ติดต่อ',
        tracking=True, copy=True, index=True, readonly=True,
        help='เซลล์ที่ติดต่อลูกค้า คัดลอกมาจากใบสั่งขายตอนออกใบแจ้งหนี้\n'
             'ล็อกไม่ให้แก้ที่ใบแจ้งหนี้ เพื่อให้ยอดค่าคอมตรงกับใบสั่งขายเสมอ '
             '(แก้ผ่านโค้ด/นำเข้าข้อมูลยังได้)')

    reason_code_id = fields.Many2one(
        'scrap.reason.code', string='ประเภทสินค้า', copy=True, index=True,
        help='ใช้แยกว่าใบนี้เป็นใบค่าปรับสินค้าหาย/ชำรุด '
             'รายงานค่าคอมนับใบพวกนี้เป็นหนี้ค้างชำระ แต่ไม่นับเป็นยอดเช่า')
