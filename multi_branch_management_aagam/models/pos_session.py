# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import hashlib
import json

from odoo import api, models, fields, _
from odoo.http import request
from odoo.tools import ustr
from odoo.exceptions import AccessError, UserError, ValidationError

class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            config_id = vals.get('config_id') or self.env.context.get('default_config_id')
            if not config_id:
                raise UserError(_("You should assign a Point of Sale to your session."))
            pos_config = self.env['pos.config'].browse(config_id)
            vals.update({'branch_id':pos_config.branch_id.id})
        return super().create(vals_list)

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True})

