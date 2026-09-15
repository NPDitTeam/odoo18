from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    asset_profile_id = fields.Many2one(
        comodel_name="account.asset.profile",
        string="Asset Profile",
        required=False,
    )
