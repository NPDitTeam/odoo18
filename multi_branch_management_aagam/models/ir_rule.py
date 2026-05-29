# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import hashlib
import json

from odoo import api, models
from odoo.http import request
from odoo.tools import ustr

import odoo


class IrRule(models.AbstractModel):
    _inherit = 'ir.rule'

    @api.model
    def _eval_context(self):
        res = super(IrRule, self)._eval_context()
        res.update(
            {
                'branch_id': self.env.user.branch_id.id,
                'branch_ids': self.env.user.branch_ids.ids,
                'multi_branch_id': self.env.user.multi_branch_id.ids
            }
        )
        return res

    def _compute_domain_keys(self):
        res = super(IrRule, self)._compute_domain_keys()
        return res



