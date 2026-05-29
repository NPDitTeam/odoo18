from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    branch_id = fields.Many2one("res.branch", string="Branch")
