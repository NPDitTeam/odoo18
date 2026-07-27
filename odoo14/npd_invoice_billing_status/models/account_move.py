# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    # สถานะวางบิล - ค่าเริ่มต้นแสดง "ยังไม่วางบิล"
    billing_status = fields.Selection([
        ('not_billed', 'ยังไม่วางบิล'),
        ('billed', 'วางบิลแล้ว'),
    ], string='สถานะวางบิล', default='not_billed', copy=False, tracking=True)

    # วางบิลให้ลูกค้าผ่านช่องทาง - แสดง/บังคับกรอก เมื่อสถานะวางบิล = วางบิลแล้ว
    billing_channel = fields.Selection([
        ('email', 'Email'),
        ('line', 'Line'),
        ('facebook', 'Facebook'),
        ('post', 'ไปรษณีย์'),
    ], string='วางบิลให้ลูกค้าผ่านช่องทาง', copy=False, tracking=True)

    # แนบหลักฐานการวางบิล (ถ่ายภาพ, แคปหน้าจอ) - แสดง/บังคับกรอก เมื่อสถานะวางบิล = วางบิลแล้ว
    billing_evidence = fields.Binary(
        string='แนบหลักฐานการวางบิล (ถ่ายภาพ,แคปหน้าจอ)',
        attachment=True,
        copy=False,
    )
    billing_evidence_filename = fields.Char(
        string='ชื่อไฟล์หลักฐานการวางบิล', copy=False,
    )
