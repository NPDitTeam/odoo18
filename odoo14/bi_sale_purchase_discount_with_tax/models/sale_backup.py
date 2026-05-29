# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

import odoo.addons.decimal_precision as dp
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning
from odoo.tools import float_is_zero, float_compare
from functools import partial
from odoo.tools.misc import formatLang, get_lang


class sale_order(models.Model):
    _inherit = 'sale.order'

    @api.depends('discount_amount', 'discount_method', 'discount_type')
    def _calculate_discount(self):
        res = 0.0
        discount = 0.0
        for self_obj in self:
            if self_obj.discount_method == 'fix':
                discount = self_obj.discount_amount
                res = discount
            elif self_obj.discount_method == 'per':
                discount = self_obj.amount_untaxed * (self_obj.discount_amount / 100)
                res = discount
            else:
                res = discount
        return res

    @api.depends('order_line', 'order_line.price_total', 'order_line.price_subtotal', \
                 'order_line.product_uom_qty', 'discount_amount', \
                 'discount_method', 'discount_type', 'order_line.discount_amount', \
                 'order_line.discount_method', 'order_line.discount_amt')
    def _amount_all(self):
        """
        Compute the total amounts of the SO.
        """
        res_config = self.env.company
        cur_obj = self.env['res.currency']
        for order in self:
            applied_discount = line_discount = sums = order_discount = amount_untaxed = amount_tax = amount_after_discount = 0.0
            amount_price_subtotal_without_discount = 0.0
            for line in order.order_line:
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax
                applied_discount += line.discount_amt
                amount_price_subtotal_without_discount += line.price_subtotal_without_discount  # (line.product_qty*line.price_unit)

                if line.discount_method == 'fix':
                    line_discount += line.discount_amount
                    if line.price_unit and line.product_qty:
                        if line.discount_amount:
                            taxes_amount_include = 0.0
                            taxes_amount_execlude = 0.0
                            if line.tax_id:
                                for tax_id in line.tax_id:
                                    if tax_id.price_include:
                                        # not calculate WTH -3 % on PO
                                        if tax_id.amount > 0:
                                            taxes_amount_include = tax_id.amount
                                    else:
                                        # not calculate WTH -3 % on PO
                                        if tax_id.amount > 0:
                                            taxes_amount_execlude = tax_id.amount
                                stwd = 0.0
                                stwd = (line.price_unit * line.product_qty) * (100 / (100 + taxes_amount_include))

                                discount_percent = (line.discount_amount / (line.product_qty * stwd)) * 100

                                # discount_percent = (line.discount_amount/((line.product_qty * line.price_unit)))*100
                                price_unit_discount = line.price_unit * (1 - (discount_percent or 0.0) / 100.0)
                                taxes_res = line.tax_id.compute_all(price_unit_discount, cur_obj, line.product_qty,
                                                                    line.product_id)
                                line.price_subtotal = stwd - line.discount_amount  # taxes_res['total_excluded']
                                # line.price_tax = sum(t.get('amount', 0.0) for t in taxes_res.get('taxes', []))
                                line.price_tax = (line.price_subtotal * (taxes_amount_include / 100)) + (
                                        line.price_subtotal * (taxes_amount_execlude / 100))
                                line.price_subtotal_without_discount = stwd
                            else:
                                line.price_subtotal = (line.product_qty * line.price_unit) - line.discount_amount
                                line.price_subtotal_without_discount = (line.product_qty * line.price_unit)
                                line.price_tax = 0

                elif line.discount_method == 'per':
                    tax = line.com_tax()
                    # line_discount += (line.price_subtotal + tax)* (line.discount_amount/ 100)
                    line_discount += (line.price_subtotal_without_discount) * (line.discount_amount / 100)

            if res_config:
                if res_config.tax_discount_policy == 'tax':
                    if order.discount_type == 'line':
                        order.discount_amt = 0.00
                        order.update({
                            'amount_untaxed': amount_untaxed,
                            'amount_tax': amount_tax,
                            'amount_total': amount_untaxed + amount_tax - line_discount,
                            'discount_amt_line': line_discount,
                        })

                    # elif order.discount_type == 'global':
                    # order.discount_amt_line = 0.00

                    # if order.discount_method == 'per':
                    #    order_discount = (amount_untaxed + amount_tax )* (order.discount_amount / 100)
                    #    order.update({
                    #        'amount_untaxed': amount_untaxed,
                    #        'amount_tax': amount_tax,
                    #        'amount_total': amount_untaxed + amount_tax - order_discount,
                    #        'discount_amt' : order_discount,
                    #    })
                    # elif order.discount_method == 'fix':
                    #    order_discount = order.discount_amount
                    #    order.update({
                    #        'amount_untaxed': amount_untaxed,
                    #        'amount_tax': amount_tax,
                    #        'amount_total': amount_untaxed + amount_tax - order_discount,
                    #        'discount_amt' : order_discount,
                    #    })
                    # else:
                    #    order.update({
                    #        'amount_untaxed': amount_untaxed,
                    #        'amount_tax': amount_tax,
                    #        'amount_total': amount_untaxed + amount_tax ,
                    #    })
                    else:
                        order.update({
                            'amount_untaxed': amount_untaxed,
                            'amount_tax': amount_tax,
                            'amount_total': amount_untaxed + amount_tax,
                        })
                elif res_config.tax_discount_policy == 'untax':
                    if order.discount_type == 'line':
                        order.discount_amt = 0.00

                        order.update({
                            'amount_untaxed': amount_untaxed,
                            'amount_tax': amount_tax,
                            # 'amount_total': amount_untaxed + amount_tax - applied_discount,
                            'amount_total': amount_untaxed + amount_tax,
                            # 'discount_amt_line' : applied_discount,
                            'discount_amt_line': line_discount,
                            'amount_price_subtotal_without_discount': amount_price_subtotal_without_discount,
                        })
                    # elif order.discount_type == 'global':
                    # order.discount_amt_line = 0.00
                    # if order.discount_method == 'per':
                    #    order_discount = amount_untaxed * (order.discount_amount / 100)
                    #    if order.order_line:
                    #        for line in order.order_line:
                    #            if line.tax_id:
                    #                final_discount = 0.0
                    #                try:
                    #                    final_discount = ((order.discount_amount*line.price_subtotal)/100.0)
                    #                except ZeroDivisionError:
                    #                    pass
                    #                discount = line.price_subtotal - final_discount
                    #                taxes = line.tax_id.compute_all(discount, \
                    #                                    order.currency_id,1.0, product=line.product_id, \
                    #                                    partner=order.partner_id)
                    #                sums += sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
                    #    order.update({
                    #        'amount_untaxed': amount_untaxed,
                    #        'amount_tax': sums,
                    #        'amount_total': amount_untaxed + sums - order_discount,
                    #        'discount_amt' : order_discount,
                    #    })
                    # elif order.discount_method == 'fix':
                    #    order_discount = order.discount_amount
                    #    if order.order_line:
                    #        for line in order.order_line:
                    #            if line.tax_id:
                    #                final_discount = 0.0
                    #                try:
                    #                    final_discount = ((order.discount_amount*line.price_subtotal)/amount_untaxed)
                    #                except ZeroDivisionError:
                    #                    pass
                    #                discount = line.price_subtotal - final_discount

                    #                taxes = line.tax_id.compute_all(discount, \
                    #                                    order.currency_id,1.0, product=line.product_id, \
                    #                                    partner=order.partner_id)
                    #                sums += sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
                    #    order.update({
                    #        'amount_untaxed': amount_untaxed,
                    #        'amount_tax': sums,
                    #        'amount_total': amount_untaxed + sums - order_discount,
                    #        'discount_amt' : order_discount,
                    #    })
                    # else:
                    #    order.update({
                    #        'amount_untaxed': amount_untaxed,
                    #        'amount_tax': amount_tax,
                    #        'amount_total': amount_untaxed + amount_tax ,
                    #    })
                    else:
                        order.update({
                            'amount_untaxed': amount_untaxed,
                            'amount_tax': amount_tax,
                            'amount_total': amount_untaxed + amount_tax,
                        })
                else:
                    order.update({
                        'amount_untaxed': amount_untaxed,
                        'amount_tax': amount_tax,
                        'amount_total': amount_untaxed + amount_tax,
                    })
            else:
                order.update({
                    'amount_untaxed': amount_untaxed,
                    'amount_tax': amount_tax,
                    'amount_total': amount_untaxed + amount_tax,
                })

    discount_method = fields.Selection([('fix', 'Fixed'), ('per', 'Percentage')], 'Discount Method')
    discount_amount = fields.Float('Discount Amount')
    discount_amt = fields.Monetary(compute='_amount_all', string='- Discount', digits='Discount', store=True,
                                   readonly=True)
    discount_type = fields.Selection([('line', 'Order Line')], string='Discount Applies to', default='line')
    # discount_type = fields.Selection([('line', 'Order Line'), ('global', 'Global')],string='Discount Applies to',default='line')
    discount_amt_line = fields.Monetary(compute='_amount_all', string='- Line Discount', digits='Line Discount',
                                        store=True, readonly=True)
    amount_price_subtotal_without_discount = fields.Float(string="Subtotal without Discount", readonly=True)

    # def _create_invoices(self, grouped=False, final=False, date=None):
    def _create_invoices(self, grouped=False, final=False):
        date = fields.Date.context_today(self)
        res = super(sale_order,self)._create_invoices(grouped=grouped, final=final)

        # res = super(sale_order, self)._create_invoices(grouped=grouped, final=final)
        res.update({'discount_type': self.discount_type})
        line_discount = 0.0
        for line in self.order_line:
            if line.discount_method == 'fix' and line.qty_delivered != 0:
                line_discount += line.discount_amount
            elif line.discount_method == 'per' and line.qty_delivered != 0:
                line_discount += line.price_subtotal * (line.discount_amount / 100)
        invoice_vals = []
        line = res.invoice_line_ids.filtered(lambda x: x.name == _('Down Payments'))
        if not line or final == False:
            res.update({'discount_method': self.discount_method,
                        'discount_amount': self.discount_amount,
                        'discount_amt': self.discount_amt,
                        'discount_amt_line': self.discount_amt_line,
                        'is_line': True, })
        else:
            pass
            #for line in res.invoice_line_ids:
            #    line.update({'discount': 0.0,
            #                 'discount_method': None,
            #                 'discount_amount': 0.0,
            #                 'discount_amt': 0.0, })

        return res

    def _amount_by_group(self):
        for order in self:
            currency = order.currency_id or order.company_id.currency_id
            fmt = partial(formatLang, self.with_context(lang=order.partner_id.lang).env, currency_obj=currency)
            res = {}
            res_config = self.env.company

            for line in order.order_line:
                price_reduce = line.price_unit * (1.0 - line.discount / 100.0)
                if res_config.tax_discount_policy == 'untax':
                    # if order.discount_type == 'global':
                    #    if order.discount_method == 'fix':
                    #        final_discount = ((order.discount_amt*line.price_subtotal)/order.amount_untaxed)
                    #        price_reduce = line.price_subtotal - final_discount
                    #    elif order.discount_method == 'per':
                    #        final_discount = ((order.discount_amount*line.price_subtotal)/100.0)
                    #        price_reduce = line.price_subtotal - final_discount
                    # *********????******** elif order.discount_type == 'line':
                    if order.discount_type == 'line':
                        if line.discount_method == 'fix':
                            price_reduce = line.price_subtotal - line.discount_amount
                        elif line.discount_method == 'per':
                            price_reduce = line.price_subtotal * (1 - (line.discount_amount / 100.0))
                taxes = line.tax_id.compute_all(price_reduce, quantity=line.product_uom_qty, product=line.product_id,
                                                partner=order.partner_shipping_id)['taxes']
                for tax in line.tax_id:
                    group = tax.tax_group_id
                    res.setdefault(group, {'amount': 0.0, 'base': 0.0})
                    for t in taxes:
                        if t['id'] == tax.id or t['id'] in tax.children_tax_ids.ids:
                            res[group]['amount'] += t['amount']
                            res[group]['base'] += t['base']
            res = sorted(res.items(), key=lambda l: l[0].sequence)
            order.amount_by_group = [(
                l[0].name, l[1]['amount'], l[1]['base'],
                fmt(l[1]['amount']), fmt(l[1]['base']),
                len(res),
            ) for l in res]

    def _prepare_invoice(self):
        res = super(sale_order, self)._prepare_invoice()
        res.update({'discount_method': self.discount_method,
                    'discount_amount': self.discount_amount,
                    'discount_amt': self.discount_amt,
                    'discount_amt_line': self.discount_amt_line,
                    'is_line': True,
                    'discount_type': self.discount_type})
        return res

    subtotal_without_discount = fields.Monetary(string="Subtotal without Discount", readonly=True,
                                                compute='_compute_subtotal_without_discount')

    def _compute_subtotal_without_discount(self):
        for record in self:
            if record.amount_price_subtotal_without_discount:
                # Assuming 'amount_price_subtotal_without_discount' is already a monetary field
                # and contains the subtotal amount before applying any discounts.
                record.subtotal_without_discount = record.amount_price_subtotal_without_discount
            else:
                # It's a good practice to set a default value if the condition is not met,
                # to avoid cache residuals on the record field.
                record.subtotal_without_discount = 0


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    def _create_invoice(self, order, so_line, amount):
        res = super(SaleAdvancePaymentInv, self)._create_invoice(order, so_line, amount)
        res.write({'discount_type': order.discount_type})
        return res


class sale_order_line(models.Model):
    _inherit = 'sale.order.line'

    @api.depends('product_qty', 'price_unit', 'tax_id', 'discount_amount')
    def com_tax(self):
        tax_total = 0.0
        tax = 0.0
        for line in self:
            for tax in line.tax_id:
                tax_total += (tax.amount / 100) * line.price_subtotal
            tax = tax_total
            return tax

    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id', 'discount_method', 'discount_amount')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        cur_obj = self.env['res.currency']
        for line in self:
            res_config = self.env.company
            if res_config:
                if res_config.tax_discount_policy == 'untax':
                    if line.discount_type == 'line':
                        if line.discount_method == 'fix':

                            if line.tax_id:
                                if line.discount_amount:
                                    if line.tax_id:
                                        if line.price_unit and line.product_qty:
                                            taxes_amount_include = 0.0
                                            taxes_amount_execlude = 0.0
                                            for taxes_id in line.tax_id:
                                                if taxes_id.price_include:
                                                    # not calculate WTH -3 % on PO
                                                    if taxes_id.amount > 0:
                                                        taxes_amount_include = taxes_id.amount
                                                else:
                                                    # not calculate WTH -3 % on PO
                                                    if taxes_id.amount > 0:
                                                        taxes_amount_execlude = taxes_id.amount

                                            stwd = 0.0
                                            stwd = (line.price_unit * line.product_qty) * (
                                                    100 / (100 + taxes_amount_include))
                                            discount_percent = (line.discount_amount / (line.product_qty * stwd)) * 100
                                            # discount_percent = (line.discount_amount/((line.product_qty * line.price_unit)))*100
                                            price_unit_discount = line.price_unit * (
                                                    1 - (discount_percent or 0.0) / 100.0)
                                            taxes_res = line.tax_id.compute_all(price_unit_discount, cur_obj,
                                                                                line.product_qty, line.product_id)
                                            # price_unit_wo_discount
                                            line.price_subtotal = stwd - line.discount_amount  # taxes_res['total_excluded']
                                            line.price_tax = (line.price_subtotal * (taxes_amount_include / 100)) + (
                                                    line.price_subtotal * (taxes_amount_execlude / 100))
                                            # line.price_tax = sum(t.get('amount', 0.0) for t in taxes_res.get('taxes', []))
                                            line.price_subtotal_without_discount = stwd
                                    else:
                                        price = (line.price_unit * line.product_qty) - line.discount_amount
                                        taxes = line.tax_id.compute_all(price, cur_obj, 1, line.product_id)
                                        line.update({
                                            'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                                            'price_total': taxes['total_included'] + line.discount_amount,
                                            'price_subtotal': taxes['total_excluded'] + line.discount_amount,
                                            'discount_amt': line.discount_amount,
                                        })
                                else:
                                    price = (line.price_unit * line.product_qty) - line.discount_amount
                                    taxes = line.tax_id.compute_all(price, cur_obj, 1, line.product_id)
                                    line.update({
                                        'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                                        'price_total': taxes['total_included'] + line.discount_amount,
                                        'price_subtotal': taxes['total_excluded'] + line.discount_amount,
                                        'discount_amt': line.discount_amount,
                                    })
                            else:
                                # case untaxs and fix discount
                                # price = (vals['price_unit'] * vals['product_qty']) - line.discount_amount
                                # taxes = line.tax_id.compute_all(price,vals['currency_id'],1,vals['product'],vals['partner'])
                                line.price_subtotal = (line.product_qty * line.price_unit) - line.discount_amount
                                line.price_subtotal_without_discount = (line.product_qty * line.price_unit)
                                line.price_tax = 0
                                line.update({
                                    # 'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                                    # 'price_total': taxes['total_included'] + line.discount_amount,
                                    # 'price_subtotal': taxes['total_excluded'] + line.discount_amount,
                                    'discount_amt': line.discount_amount,
                                })
                                # price = (line.price_unit * line.product_uom_qty) - line.discount_amount
                            # taxes = line.tax_id.compute_all(price, line.order_id.currency_id, 1, product=line.product_id, partner=line.order_id.partner_shipping_id)
                            # line.price_subtotal_without_discount = 12345
                            # print("---Sale--------11111111111---------line.price_subtotal_without_discount = " , line.price_subtotal_without_discount)
                            # line.update({
                            # 'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                            # 'price_total': taxes['total_included'] + line.discount_amount,
                            # 'price_subtotal': taxes['total_excluded'] + line.discount_amount,
                            # 'discount_amt' : line.discount_amount,

                            # })
                        elif line.discount_method == 'per':
                            taxes_amount_include = 0.0
                            taxes_amount_execlude = 0.0
                            if line.tax_id:
                                for taxes_id in line.tax_id:
                                    if taxes_id.price_include:
                                        # not calculate WTH -3 % on PO
                                        if taxes_id.amount > 0:
                                            taxes_amount_include = taxes_id.amount
                                        if line.discount_amount > 0:
                                            line.discount_amt = (line.price_unit * line.product_qty) * (
                                                    100 / (100 + taxes_amount_include)) * line.discount_amount / 100
                                    else:
                                        # not calculate WTH -3 % on PO
                                        if taxes_id.amount > 0:
                                            taxes_amount_execlude = taxes_id.amount
                                        if line.discount_amount > 0:
                                            line.discount_amt = (
                                                                        line.product_qty * line.price_unit) * line.discount_amount / 100

                            stwd = 0.0
                            stwd = (line.price_unit * line.product_qty) * (100 / (100 + taxes_amount_include))
                            price = (line.price_unit * line.product_qty) * (1 - (line.discount_amount or 0.0) / 100.0)
                            # price_x = ((vals['price_unit'] * vals['product_qty'])-((vals['price_unit'] * vals['product_qty']) * (1 - (line.discount_amount or 0.0) / 100.0)))
                            taxes = line.tax_id.compute_all(price, cur_obj, 1, line.product_id)
                            if line.discount_amount > 0:
                                line.discount_amt = (line.product_qty * line.price_unit) * line.discount_amount / 100
                            line.price_subtotal_without_discount = stwd
                            line.update({
                                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                                # 'price_total': taxes['total_included'] + price_x,
                                # 'price_subtotal': taxes['total_excluded'] + price_x,
                                'price_total': taxes['total_included'],
                                'price_subtotal': taxes['total_excluded'],
                                'discount_amt': line.discount_amt,
                            })
                            # price = (line.price_unit * line.product_uom_qty) * (1 - (line.discount_amount or 0.0) / 100.0)
                            # price_x = ((line.price_unit * line.product_uom_qty) - (line.price_unit * line.product_uom_qty) * (1 - (line.discount_amount or 0.0) / 100.0))
                            # taxes = line.tax_id.compute_all(price, line.order_id.currency_id, 1, product=line.product_id, partner=line.order_id.partner_shipping_id)
                            # line.update({
                            #    'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                            #    'price_total': taxes['total_included'] + price_x,
                            #    'price_subtotal': taxes['total_excluded'] + price_x,
                            #    'discount_amt' : price_x,
                            # })
                        else:
                            taxes_amount_include = 0.0
                            taxes_amount_execlude = 0.0
                            if line.tax_id:
                                for taxes_id in line.tax_id:
                                    if taxes_id.price_include:
                                        # not calculate WTH -3 % on PO
                                        if taxes_id.amount > 0:
                                            taxes_amount_include = taxes_id.amount
                                    else:
                                        # not calculate WTH -3 % on PO
                                        if taxes_id.amount > 0:
                                            taxes_amount_execlude = taxes_id.amount
                            taxes_res = line.tax_id.compute_all(line.price_unit, cur_obj, line.product_qty,
                                                                line.product_id)
                            stwd = 0.0
                            stwd = (line.price_unit * line.product_qty) * (100 / (100 + taxes_amount_include))
                            line.price_subtotal_without_discount = stwd
                            line.price_tax = sum(t.get('amount', 0.00000) for t in taxes_res.get('taxes', []))
                            taxes = line.tax_id.compute_all(line.price_unit, cur_obj, line.product_qty, line.product_id)
                            line.update({
                                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                                'price_total': taxes['total_included'],
                                'price_subtotal': taxes['total_excluded'],
                            })

                            # price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                            # taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty, product=line.product_id, partner=line.order_id.partner_shipping_id)
                            # line.update({
                            # 'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                            # 'price_total': taxes['total_included'],
                            # 'price_subtotal': taxes['total_excluded'],
                            # })
                    else:
                        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                        taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty,
                                                        product=line.product_id,
                                                        partner=line.order_id.partner_shipping_id)

                        line.update({
                            'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                            'price_total': taxes['total_included'],
                            'price_subtotal': taxes['total_excluded'],
                        })
                elif res_config.tax_discount_policy == 'tax':
                    if line.discount_type == 'line':
                        price_x = 0.0
                        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                        taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty,
                                                        product=line.product_id,
                                                        partner=line.order_id.partner_shipping_id)

                        if line.discount_method == 'fix':
                            price_x = (taxes['total_included']) - (taxes['total_included'] - line.discount_amount)
                        elif line.discount_method == 'per':
                            price_x = (taxes['total_included']) - (
                                    taxes['total_included'] * (1 - (line.discount_amount or 0.0) / 100.0))
                        else:
                            price_x = line.price_unit * (1 - (line.discount or 0.0) / 100.0)

                        line.update({
                            'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                            'price_total': taxes['total_included'],
                            'price_subtotal': taxes['total_excluded'],
                            'discount_amt': price_x,
                        })
                    else:
                        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                        taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty,
                                                        product=line.product_id,
                                                        partner=line.order_id.partner_shipping_id)
                        line.update({
                            'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                            'price_total': taxes['total_included'],
                            'price_subtotal': taxes['total_excluded'],
                        })
                else:
                    price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                    taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty,
                                                    product=line.product_id, partner=line.order_id.partner_shipping_id)

                    line.update({
                        'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                        'price_total': taxes['total_included'],
                        'price_subtotal': taxes['total_excluded'],
                    })
            else:
                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                taxes = line.tax_id.compute_all(price, line.order_id.currency_id, line.product_uom_qty,
                                                product=line.product_id, partner=line.order_id.partner_shipping_id)

                line.update({
                    'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                    'price_total': taxes['total_included'],
                    'price_subtotal': taxes['total_excluded'],
                })

    is_apply_on_discount_amount = fields.Boolean("Tax Apply After Discount")
    discount_method = fields.Selection([('fix', 'Fixed'), ('per', 'Percentage')], 'Discount Method')
    discount_type = fields.Selection(related='order_id.discount_type', string="Discount Applies to")
    discount_amount = fields.Float('Discount Amount')
    discount_amt = fields.Float('Discount Final Amount')
    price_subtotal_without_discount = fields.Float(compute='_compute_amount', string="Subtotal without Discount",
                                                   readonly=True, store=True)

    def _prepare_invoice_line(self, **optional_values):
        res = super(sale_order_line, self)._prepare_invoice_line(**optional_values)
        discount_percent = 0
        line = self
        if line.discount_method == 'fix':
            if line.tax_id:
                taxes_amount_include = 0.0
                taxes_amount_execlude = 0.0
                for tax_id in line.tax_id:
                    if tax_id.price_include:
                        # not calculate WTH -3 % on PO
                        if tax_id.amount > 0:
                            taxes_amount_include = tax_id.amount
                    else:
                        # not calculate WTH -3 % on PO
                        if tax_id.amount > 0:
                            taxes_amount_execlude = tax_id.amount
                stwd = 0.0
                stwd = (line.price_unit * line.product_qty) * (100 / (100 + taxes_amount_include))
                if (line.product_qty * stwd) > 0 :
                    discount_percent = (line.discount_amount / (line.product_qty * stwd)) * 100
        elif line.discount_method == 'per':
            discount_percent = line.discount_amount
        else:
            if (line.product_qty * line.price_unit) > 0:
                discount_percent = line.discount_amount / ((line.product_qty * line.price_unit) * 100)
        res.update({'discount': self.discount,
                    'discount_method': self.discount_method,
                    'discount_amount': self.discount_amount,
                    'discount_amt': self.discount_amt,
                    'discount': discount_percent})
        return res

    discount_amount_text = fields.Char(string='Discount Text', readonly=True,
                                       compute='_compute_discount_values')

    @api.depends('discount_method', 'discount_amount')
    def _compute_discount_values(self):
        for record in self:
            if record.discount_method == 'per':
                # Assuming discount_amount stores the percentage value in this case
                record.discount_amount_text = "{:,.0f}%".format(record.discount_amount)
            else:
                # Here, discount_amount stores the actual monetary value
                record.discount_amount_text = "{:,.2f} {}".format(record.discount_amount, record.currency_id.symbol)


class ResCompany(models.Model):
    _inherit = 'res.company'

    tax_discount_policy = fields.Selection([('tax', 'Tax Amount'), ('untax', 'Untax Amount')],
                                           default_model='sale.order', default='untax')
    sale_account_id = fields.Many2one('account.account',
                                      domain=[('user_type_id.name', '=', 'Expenses'), ('discount_account', '=', True)])
    purchase_account_id = fields.Many2one('account.account', domain=[('user_type_id.name', '=', 'Income'),
                                                                     ('discount_account', '=', True)])


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tax_discount_policy = fields.Selection([('tax', 'Tax Amount'), ('untax', 'Untax Amount')], readonly=False,
                                           related='company_id.tax_discount_policy', string='Discount Applies On',
                                           default_model='sale.order'
                                           )
    sale_account_id = fields.Many2one('account.account', string='Sale Discount Account', check_company=True,
                                      domain=[('user_type_id.name', '=', 'Expenses'), ('discount_account', '=', True)],
                                      readonly=False, related='company_id.sale_account_id')
    purchase_account_id = fields.Many2one('account.account', string='Purchase Discount Account', check_company=True,
                                          domain=[('user_type_id.name', '=', 'Income'),
                                                  ('discount_account', '=', True)], readonly=False,
                                          related='company_id.purchase_account_id')
