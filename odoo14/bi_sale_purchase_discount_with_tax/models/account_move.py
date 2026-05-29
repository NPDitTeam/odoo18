# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
# Rewritten for Odoo 18 compatibility

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class account_account(models.Model):
    _inherit = 'account.account'
    discount_account = fields.Boolean('Discount Account')


class account_move(models.Model):
    _inherit = 'account.move'

    is_line = fields.Boolean('Is a line')
    discount_method = fields.Selection([('fix', 'Fixed'), ('per', 'Percentage')], 'Discount Method')
    discount_amount = fields.Float('Discount Amount')
    discount_type = fields.Selection([('line', 'Order Line')], 'Discount Applies to', default='line')
    discount_account_id = fields.Many2one('account.account', 'Discount Account')
    discount_amount_line = fields.Float(string="Discount Line")

    discount_amt = fields.Float(
        string='- Discount', digits='Discount', store=True, readonly=True,
        compute='_compute_discount_totals',
    )
    discount_amt_line = fields.Float(
        string='- Line Discount', digits='Discount', store=True, readonly=True,
        compute='_compute_discount_totals',
    )
    amount_price_subtotal_without_discount = fields.Float(
        string="Subtotal without Discount", readonly=True, store=True,
        compute='_compute_discount_totals',
    )
    amount_price_total_full = fields.Float(
        string="Total Amount (Full)", store=True, digits='Product Price',
        compute='_compute_amount_price_total_full',
        help='Total full amount from all lines without discount and tax: Sum of (Price Unit x Quantity)',
    )
    discount_amount_computed = fields.Float(
        string='Computed Discount', store=True, digits='Discount',
        compute='_compute_discount_amount_computed',
        help='Calculate discount amount based on discount_method',
    )

    def calc_discount(self):
        for calculate in self:
            calculate._compute_discount_totals()

    @api.depends('invoice_line_ids.price_total_full')
    def _compute_amount_price_total_full(self):
        for move in self:
            move.amount_price_total_full = sum(line.price_total_full for line in move.invoice_line_ids)

    @api.depends('invoice_line_ids.discount_amount_computed', 'invoice_line_ids.discount_method', 'invoice_line_ids.discount_amount')
    def _compute_discount_amount_computed(self):
        for move in self:
            total_discount = 0.0
            for line in move.invoice_line_ids:
                if line.discount_method == 'fix':
                    total_discount += line.discount_amount
                elif line.discount_method == 'per':
                    total_price = line.price_unit * line.quantity
                    total_discount += total_price * (line.discount_amount / 100.0)
            move.discount_amount_computed = total_discount

    @api.depends(
        'invoice_line_ids.discount_method', 'invoice_line_ids.discount_amount',
        'invoice_line_ids.price_subtotal', 'invoice_line_ids.price_subtotal_without_discount',
        'discount_type', 'discount_method', 'discount_amount',
    )
    def _compute_discount_totals(self):
        for move in self:
            line_discount = 0.0
            subtotal_wo_disc = 0.0
            for line in move.invoice_line_ids:
                subtotal_wo_disc += line.price_subtotal_without_discount
                if line.discount_method == 'per':
                    line_discount += line.price_subtotal_without_discount * (line.discount_amount / 100.0)
                elif line.discount_method == 'fix':
                    line_discount += line.discount_amount

            move.discount_amt_line = line_discount
            move.amount_price_subtotal_without_discount = subtotal_wo_disc

            # Global discount
            if move.discount_type != 'line' and move.discount_method:
                if move.discount_method == 'fix':
                    move.discount_amt = move.discount_amount
                elif move.discount_method == 'per':
                    move.discount_amt = move.amount_untaxed * (move.discount_amount / 100.0)
                else:
                    move.discount_amt = 0.0
            else:
                move.discount_amt = 0.0

    def _prepare_invoice(self):
        res = super()._prepare_invoice()
        return res


class account_move_line(models.Model):
    _inherit = 'account.move.line'

    discount_method = fields.Selection([('fix', 'Fixed'), ('per', 'Percentage')], 'Discount Method')
    discount_type = fields.Selection(related='move_id.discount_type', string="Discount Applies to")
    discount_amount = fields.Float('Discount Amount')
    discount_amt = fields.Float('Discount Final Amount')

    price_total_full = fields.Float(
        string='Total Amount (Full)', compute='_compute_price_total_full', store=True,
        digits='Product Price', help='Full amount without discount and tax: Price Unit x Quantity',
    )
    price_subtotal_without_discount = fields.Float(
        string="Subtotal without Discount", compute='_compute_price_subtotal_without_discount',
        store=True, readonly=True,
    )
    discount_amount_computed = fields.Float(
        string='Computed Discount Amount', compute='_compute_discount_amount_computed',
        store=True, digits='Discount',
        help='Calculate discount amount based on discount_method',
    )

    @api.depends('price_unit', 'quantity')
    def _compute_price_total_full(self):
        for line in self:
            line.price_total_full = line.price_unit * line.quantity

    @api.depends('price_unit', 'quantity', 'tax_ids', 'discount_method', 'discount_amount')
    def _compute_price_subtotal_without_discount(self):
        for line in self:
            taxes_amount_include = 0.0
            if line.tax_ids:
                for tax in line.tax_ids:
                    if tax.price_include and tax.amount > 0:
                        taxes_amount_include = tax.amount
            if taxes_amount_include > 0:
                line.price_subtotal_without_discount = (line.price_unit * line.quantity) * (100 / (100 + taxes_amount_include))
            else:
                line.price_subtotal_without_discount = line.price_unit * line.quantity

    @api.depends('discount_method', 'discount_amount', 'price_unit', 'quantity')
    def _compute_discount_amount_computed(self):
        for line in self:
            if line.discount_method == 'fix':
                line.discount_amount_computed = line.discount_amount
            elif line.discount_method == 'per':
                total_price = line.price_unit * line.quantity
                line.discount_amount_computed = total_price * (line.discount_amount / 100.0)
            else:
                line.discount_amount_computed = 0.0

    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'discount_method', 'discount_amount')
    def com_tax(self):
        tax_total = 0.0
        for line in self:
            for tax in line.tax_ids:
                tax_total += (tax.amount / 100) * line.price_subtotal
            return tax_total
