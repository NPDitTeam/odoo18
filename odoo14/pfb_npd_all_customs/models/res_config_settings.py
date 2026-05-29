from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    deposit_default_npd_id = fields.Many2one(
        'product.product',
        'เงินประกัน',
        domain="[('type', '=', 'service')]",
        config_parameter='sale.deposit_default_npd_id',)
