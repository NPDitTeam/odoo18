# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import hashlib
import json

from odoo import api, models, fields, _
from odoo.http import request
from odoo.tools import ustr


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            session_id = vals.get('session_id')
            session_config = self.env['pos.session'].browse(session_id)
            vals.update({'branch_id':session_config.branch_id.id})
        return super().create(vals_list)

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True})


class PosPaymentMethod(models.Model):

    _inherit = 'pos.payment.method'

    # @api.model_create_multi
    # def create(self, vals_list):
    #     for vals in vals_list:
    #         config_id = vals.get('config_ids')[0]
    #         pos_config = self.env['pos.config'].browse(config_id)
    #         vals.update({'branch_id':pos_config.branch_id.id})
    #     return super().create(vals_list)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            config_ids = vals.get('config_ids')
            if config_ids and isinstance(config_ids, list):
                config_id = config_ids[0]
                pos_config = self.env['pos.config'].browse(config_id)
                vals.update({'branch_id': pos_config.branch_id.id})
        return super().create(vals_list)

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True})
