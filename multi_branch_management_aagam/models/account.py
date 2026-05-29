# -*- coding: utf-8 -*-

from odoo import fields, models, tools
from odoo.tools import SQL

class AccountInvoiceReport(models.Model):
    """inherited invoice report"""
    _inherit = "account.invoice.report"

    branch_id = fields.Many2one('res.branch', 'Branch', readonly=True)

    def _select(self) -> SQL:
        return SQL("%s, move.branch_id as branch_id", super()._select())

class Account(models.Model):
    _inherit = 'account.account'

    activity_type = fields.Selection(
        [('operation_income', 'Operation-Income'),
         ('operation_expense', 'Operation-Expense'),
         ('operation_current_asset', 'Operation-Current Asset'),
         ('operation_current_liability', 'Operation-Current Liability'),
         ('investing', 'Investing'),
         ('financing', 'Financing')], string='Activity Type')

