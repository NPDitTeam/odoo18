from odoo import api, fields, models
from dateutil.relativedelta import relativedelta


class AccountMoveTaxInvoice(models.Model):
    _name = 'account.move.tax.invoice'
    _description = 'Tax Invoice'

    tax_invoice_number = fields.Char(string='เลขที่ใบกำกับภาษี')
    tax_invoice_date = fields.Date(string='วันที่ใบกำกับภาษี')
    report_late_mo = fields.Selection([
        ('0', 'เดือนปัจจุบัน'),
        ('1', 'ย้อนหลัง 1 เดือน'),
        ('2', 'ย้อนหลัง 2 เดือน'),
        ('3', 'ย้อนหลัง 3 เดือน'),
        ('4', 'ย้อนหลัง 4 เดือน'),
        ('5', 'ย้อนหลัง 5 เดือน'),
        ('6', 'ย้อนหลัง 6 เดือน'),
    ], string='รายงานล่าช้า', default='0')
    report_date = fields.Date(string='วันที่รายงาน', compute='_compute_report_date', store=True)
    move_line_id = fields.Many2one('account.move.line', string='Journal Item', ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Partner')
    move_id = fields.Many2one('account.move', string='Journal Entry', ondelete='cascade', index=True)
    move_state = fields.Selection(related='move_id.state', store=True)
    payment_id = fields.Many2one('account.payment', string='Payment', compute='_compute_payment_id')
    to_clear_tax = fields.Boolean(string='Clear Tax')
    company_id = fields.Many2one('res.company', string='Company', related='move_id.company_id', store=True)
    account_id = fields.Many2one('account.account', string='Account', related='move_line_id.account_id')
    tax_line_id = fields.Many2one('account.tax', string='Tax', related='move_line_id.tax_line_id')
    tax_base_amount = fields.Monetary(string='Tax Base', related='move_line_id.tax_base_amount')
    balance = fields.Monetary(string='Balance', related='move_line_id.balance')
    currency_id = fields.Many2one('res.currency', related='move_id.currency_id')

    # Fields required by account_advance module
    advance_clear_id = fields.Many2one('account.advance.clear', string='Account Clear', ondelete='cascade')
    reversing_id = fields.Many2one('account.move.tax.invoice', string='Reversing Tax Invoice')
    reversed_id = fields.Many2one('account.move.tax.invoice', string='Reversed Tax Invoice')

    @api.depends('tax_invoice_date', 'report_late_mo')
    def _compute_report_date(self):
        for rec in self:
            if rec.tax_invoice_date and rec.report_late_mo:
                rec.report_date = rec.tax_invoice_date + relativedelta(months=int(rec.report_late_mo))
            else:
                rec.report_date = rec.tax_invoice_date

    def _compute_payment_id(self):
        for rec in self:
            if rec.move_id:
                payment = self.env['account.payment'].search([('move_id', '=', rec.move_id.id)], limit=1)
                rec.payment_id = payment.id if payment else False
            else:
                rec.payment_id = False
