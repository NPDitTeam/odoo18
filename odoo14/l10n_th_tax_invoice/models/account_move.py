from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    tax_invoice_ids = fields.One2many('account.move.tax.invoice', 'move_line_id', string='Tax Invoices')
    manual_tax_invoice = fields.Boolean(string='Manual Tax Invoice')


class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_ids = fields.One2many('account.move.tax.invoice', 'move_id', string='Tax Invoices')
