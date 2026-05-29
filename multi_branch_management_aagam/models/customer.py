# -*- coding: utf-8 -*-

from odoo import api, fields, models
import datetime


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_branch = fields.Boolean('Is Branch')
    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True},
                                compute="_compute_branch", store=True)
                                # default=lambda self: self.env.user.branch_id.id)

    @api.depends('name')
    def _compute_branch(self):
        for res_id in self:
            if res_id and res_id.is_branch:
                res_id.branch_id = None
            else:
                res_id.branch_id = res_id.env.user.branch_id
