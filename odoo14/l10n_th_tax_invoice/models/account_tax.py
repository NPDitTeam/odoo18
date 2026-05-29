from odoo import fields, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    taxinv_sequence_id = fields.Many2one('ir.sequence', string='Tax Invoice Sequence')
