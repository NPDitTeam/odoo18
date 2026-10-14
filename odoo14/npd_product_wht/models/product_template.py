# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    wht_category_id = fields.Many2one('wht.category', string='หมวดหมู่ WHT',
                                      help='หมวดหมู่ภาษีหัก ณ ที่จ่าย สำหรับสินค้า/บริการนี้')
    wht_rate_display = fields.Selection(related='wht_category_id.wht_rate', string='อัตรา WHT')
