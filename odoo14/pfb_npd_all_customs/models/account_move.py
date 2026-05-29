import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    debt_payment_type = fields.Selection([
        ('cash', 'เงินสด'),
        ('transfer', 'โอนเงิน'),
        ('cheque', 'เช็ค'),
    ], string='ประเภทการรับชำระหนี้')

    contact_type = fields.Selection([
        ('branch', 'สาขา'),
        ('sale', 'Sales'),
    ], string='การติดต่อของลูกค้า')

    sales_contact = fields.Many2one('res.users', string='Sales ที่ติดต่อ')

    pfb_so_type = fields.Selection([
        ('sale', 'Sales'),
        ('rent', 'Rent')],
        string="Sale Type",
        index=True, default='sale', required=True)

    pfb_date_of_rent = fields.Integer(string="Day of Rent")
    pfb_objective_id = fields.Many2one('sale.objective', string="Objective")
    pfb_amount_insurance = fields.Float('Insurance Amount', digits=0)
    pfb_dis_amount_insurance = fields.Float('Insurance Discount', digits=0)
    pfb_amount = fields.Float('Net Insurance', digits=0)

    # discount_amt_line comes from bi_sale_purchase_discount_with_tax module
    # Define it here as fallback if that module is not installed
    discount_amt_line = fields.Monetary(
        string='- Line Discount',
        store=True,
        compute='_compute_total_rental_discount',
    )

    total_rental_discount = fields.Float(
        string="- Rental Discount",
        compute="_compute_total_rental_discount",
        store=True
    )

    @api.depends("invoice_line_ids.discount_type_selection")
    def _compute_total_rental_discount(self):
        for move in self:
            rental_discount = 0.0
            product_discount = 0.0
            for line in move.invoice_line_ids:
                discount_amount = getattr(line, 'discount_amount', 0.0) or 0.0
                if line.discount_type_selection == 'rental':
                    rental_discount += discount_amount
                elif not line.discount_type_selection or line.discount_type_selection == 'product':
                    product_discount += discount_amount
            move.total_rental_discount = rental_discount
            move.discount_amt_line = product_discount


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    pfb_so_rent_ok = fields.Boolean('Can be Rent')
    move_type_parent = fields.Selection(related='move_id.move_type', store=True)
    move_state_parent = fields.Selection(related='move_id.state', store=True)
    pfb_date_of_rent = fields.Integer(string="Day of Rent", store=True)
    pfb_quantity = fields.Integer(string="Quantity Rent", store=True)
    pfb_insurance_price = fields.Float(string="Insurance")
    pfb_objective_id = fields.Many2one('sale.objective', string="Objective")
    discount_type_selection = fields.Selection(
        [
            ('product', 'Product Discount'),
            ('rental', 'Rental Discount')
        ],
        string="Discount Type",
        default='product'
    )

    @api.onchange('pfb_date_of_rent', 'pfb_quantity')
    def _onchange_pfb_date_of_rent(self):
        if self.move_id and self._origin and self._origin.id:
            self.env.cr.execute("""
                UPDATE account_move_line
                SET pfb_date_of_rent = %s,
                    pfb_quantity = %s
                WHERE id = %s
            """, (
                self.pfb_date_of_rent or 0,
                self.pfb_quantity or 0,
                self._origin.id
            ))
