from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    npd_rent_ok = fields.Boolean('Can be Rent', default=False)



