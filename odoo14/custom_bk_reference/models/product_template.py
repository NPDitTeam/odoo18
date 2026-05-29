from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    bk_reference_code = fields.Char(string="รหัสอ้างอิงบ้านเขียว")
