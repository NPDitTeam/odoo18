from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    to_clear_tax = fields.Boolean(string='Clear VAT')
    tax_invoice_ids = fields.One2many('account.move.tax.invoice', 'payment_id', string='Tax Invoices')

    # Field required by account_advance module (One2many inverse_name)
    advance_clear_id = fields.Many2one('account.advance.clear', string='Advance Clear', ondelete='set null')
