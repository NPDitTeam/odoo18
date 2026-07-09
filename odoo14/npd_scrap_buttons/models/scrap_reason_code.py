# -*- coding: utf-8 -*-
from odoo import fields, models


class ScrapReasonCode(models.Model):
    _inherit = 'scrap.reason.code'

    is_damage_repair = fields.Boolean(
        string='ต้องส่งซ่อม',
        help='ถ้าเปิดไว้ เมื่อสร้าง Scrap ด้วย Reason Code นี้ '
             'เอกสารจะเข้าสถานะ "รอดำเนินการแจ้งซ่อม" แทน "เสร็จสิ้น"'
    )
