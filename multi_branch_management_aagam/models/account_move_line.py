# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # activity_type = fields.Selection(related='user_type_id.activity_type')
    user_type_id = fields.Many2one('account.account', string='Type',
        help="Account Type is used for information purpose, to generate country-specific legal reports, and set the rules to close a fiscal year and generate opening entries.")

