# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountVoucher(models.Model):
    _inherit = 'account.voucher'

    # ผูกกลับไปหาคำขอ — ฝ่ายบัญชีเปิดดูต้นเรื่องได้ และใช้กรองเมนูใบค่ารักษาพยาบาล
    hrms_medical_log_id = fields.Many2one(
        'hr.manual.time.log', string='คำขอค่ารักษาพยาบาล',
        readonly=True, copy=False, index=True, ondelete='set null')
