from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class AdvanceClearLineAI(models.Model):
    _inherit = 'advance.clear.line'

    account_analytic_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        required=True,
    )
