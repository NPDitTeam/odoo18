from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    reason_code_id = fields.Many2one("scrap.reason.code", string="Reason code")
