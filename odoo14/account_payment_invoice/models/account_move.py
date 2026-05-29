from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_ids = fields.One2many(
        'account.move.tax.invoice', 'move_id', string='Tax Invoices',
    )
    payment_id = fields.Many2one(
        'account.payment', string='Payment', copy=False,
    )
    total_debit = fields.Monetary(
        string='รวมเดบิต', compute='_compute_total_debit_credit',
        currency_field='currency_id',
    )
    total_credit = fields.Monetary(
        string='รวมเครดิต', compute='_compute_total_debit_credit',
        currency_field='currency_id',
    )

    @api.depends('line_ids.debit', 'line_ids.credit')
    def _compute_total_debit_credit(self):
        for move in self:
            move.total_debit = sum(move.line_ids.mapped('debit'))
            move.total_credit = sum(move.line_ids.mapped('credit'))

    def _post(self, soft=True):
        """Override: handle tax invoice info before/after posting.

        Purchase tax → use vendor info (tax_invoice_number, tax_invoice_date).
        Sales tax → auto-generate number from sequence, compute tax_base from paid_total.
        """
        # ---- Purchase Taxes: validate before posting ----
        for move in self:
            for tax_invoice in move.tax_invoice_ids.filtered(
                lambda l: l.tax_line_id.type_tax_use == 'purchase'
                or (
                    l.move_id.move_type == 'entry'
                    and not l.payment_id
                    and l.move_id.journal_id.type != 'sale'
                )
            ):
                if (
                    not tax_invoice.tax_invoice_number
                    or not tax_invoice.tax_invoice_date
                ):
                    if tax_invoice.payment_id:
                        tax_invoice.payment_id.write({'to_clear_tax': True})
                        return self.browse()
                    elif self.mapped('move_type') == ['entry', 'entry']:
                        return self.browse()
                    else:
                        return self.browse()

        # ---- Standard posting ----
        res = super()._post(soft)

        # ---- Sales Taxes: auto-fill after posting ----
        for move in self:
            for tax_invoice in move.tax_invoice_ids.filtered(
                lambda l: l.tax_line_id.type_tax_use == 'sale'
            ):
                try:
                    payment = tax_invoice.payment_id
                    tax_base = 0

                    if payment and payment.custom_invoice_ids:
                        matching_inv_line = payment.custom_invoice_ids[0]

                        if (
                            matching_inv_line
                            and matching_inv_line.paid_total > 0
                        ):
                            tax_rate = tax_invoice.tax_line_id.amount / 100.0
                            tax_base = (
                                matching_inv_line.paid_total / (1.0 + tax_rate)
                            )

                            tinv_number, _ = self._get_tax_invoice_number(
                                move, tax_invoice, tax_invoice.tax_line_id,
                            )

                            tax_invoice.write({
                                'tax_invoice_number': tinv_number,
                                'tax_invoice_date': payment.date,
                                'tax_base_amount': tax_base,
                                'partner_id': payment.partner_id.id,
                            })
                    else:
                        tinv_number, tinv_date = self._get_tax_invoice_number(
                            move, tax_invoice, tax_invoice.tax_line_id,
                        )
                        tax_invoice.write({
                            'tax_invoice_number': tinv_number,
                            'tax_invoice_date': tinv_date,
                            'partner_id': move.partner_id.id,
                        })

                except Exception as e:
                    _logger.warning(
                        'Error updating tax invoice for %s: %s',
                        tax_invoice, e,
                    )

        # ---- Check tax invoice amounts ----
        for move in self:
            try:
                move.line_ids._checkout_tax_invoice_amount()
            except Exception:
                pass

        return res
