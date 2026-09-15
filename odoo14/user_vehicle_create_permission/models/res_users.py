# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    can_create_vehicle = fields.Boolean(
        string='สามารถสร้างยานพาหนะได้',
        default=False,
        help='ติ๊กเพื่ออนุญาตให้ผู้ใช้รายนี้สร้างยานพาหนะใหม่ได้\n'
             'ไม่ติ๊ก = สร้างไม่ได้ แต่ยังดูและแก้ไขคันที่มีอยู่ได้ตามสิทธิ์เดิม')
