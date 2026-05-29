# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from datetime import datetime


class BiProductPricelist(models.Model):
    _inherit = "product.pricelist"

    pricelist_branch_id = fields.Many2one('res.branch', string='Branch')


class BiProductItemPricelist(models.Model):
    _inherit = "product.pricelist.item"

    branch_id = fields.Many2one('res.branch', string='Branch', readonly=True,
                                related='pricelist_id.pricelist_branch_id', store=True)
