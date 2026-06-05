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
        user = self.env.user
        active_company_ids = set(self.env.companies.ids)
        # Branches the user may use that belong to the currently active
        # company/companies (a branch with no company is treated as shared).
        in_company = user.branch_ids.filtered(
            lambda b: (not b.company_ids) or (set(b.company_ids.ids) & active_company_ids)
        )
        # Active navbar selection, limited to the current company. If the stored
        # selection has nothing in this company (e.g. right after switching
        # company), fall back to all of this company's branches so the user
        # still sees that company's data instead of an empty list.
        selected = user.multi_branch_id.filtered(lambda b: b in in_company)
        effective = selected or in_company
        res.update(
            {
                'branch_id': user.branch_id.id,
                'branch_ids': user.branch_ids.ids,
                'multi_branch_id': effective.ids,
            }
        )
        return res

    def _compute_domain_keys(self):
        res = super(IrRule, self)._compute_domain_keys()
        return res



