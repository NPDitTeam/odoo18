# -*- coding: utf-8 -*-
from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    can_confirm_refund_payment = fields.Boolean(
        string='สามารถยืนยัน/ยกเลิกเอกสารคืนเงิน',
        default=False,
        help='ถ้าเลือกไว้ ผู้ใช้จะสามารถกดปุ่มยืนยันและยกเลิกเอกสารคืนเงินได้'
    )

    allow_edit_refund_date = fields.Boolean(
        string='อนุญาตให้แก้ไขวันที่ในเอกสารคืนเงิน',
        default=False,
        help='ถ้าเลือกไว้ ผู้ใช้จะสามารถแก้ไขวันที่ในเอกสารคืนเงินได้'
    )
