from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    can_create_product = fields.Boolean(
        string='สามารถสร้างสินค้าได้',
        default=False,
        help='เลือกเพื่ออนุญาตให้ผู้ใช้สร้างสินค้าใหม่ได้'
    )
