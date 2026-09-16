# -*- coding: utf-8 -*-

from odoo import models


class AccountAdvanceClear(models.Model):
    """เมนู Avance Clear"""

    _name = 'account.advance.clear'
    _inherit = ['account.advance.clear', 'npd.expense.review.mixin']
