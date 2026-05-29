from odoo import models, fields, api, _


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist.item'

    npd_insurance_price = fields.Float('Insurance Price', digits='Product Price')
