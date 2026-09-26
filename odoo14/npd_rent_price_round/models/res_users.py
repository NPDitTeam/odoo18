# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    can_edit_use_new_calc = fields.Boolean(
        string='แก้วิธีคิดราคาต่อหน่วยได้',
        help='ปิดอยู่ = เห็นค่าได้แต่แก้ไม่ได้ กันคนเผลอสลับวิธีคิดยอด '
             'ซึ่งจะทำให้ยอดทั้งใบเปลี่ยน')
