# -*- coding: utf-8 -*-

from odoo import api, fields, models
import datetime


class StockInventory(models.Model):
    _inherit = "stock.inventory"

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True},  default=lambda self: self.env.user.branch_id.id)
