# -*- coding: utf-8 -*-

from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    allow_edit_invoice_date = fields.Boolean(
        string='อนุญาตให้แก้ไขวันที่ Invoice',
        default=False,
        help='เมื่อเปิดใช้งาน ผู้ใช้สามารถแก้ไขวันที่ Invoice Date ได้'
    )
