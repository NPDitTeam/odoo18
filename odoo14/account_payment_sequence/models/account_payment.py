from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def get_seq_payment(self):
        if self.payment_type == 'inbound':
            return self.env['ir.sequence'].next_by_code('customer.payment') or '/'
        else:
            return self.env['ir.sequence'].next_by_code('supplier.payment') or '/'

    def action_post(self):
        """Override action_post to replace journal sequence with custom sequence + auto-reconcile"""
        res = super().action_post()
        for payment in self:
            if not payment.move_id:
                continue

            # 1. Replace sequence via SQL (bypass Odoo 18 constraints)
            seq_name = payment.get_seq_payment()
            if seq_name and seq_name != '/':
                self.env.cr.execute(
                    "UPDATE account_move SET name = %s WHERE id = %s",
                    (seq_name, payment.move_id.id),
                )
                payment.move_id.invalidate_recordset(['name'])

            # 2. voucher_source_id is Many2one to account.payment (NOT account.move)
            # ไม่ set ที่นี่ — ใช้ voucher_number แทน

            # 3. Copy memo/ref from invoice to move
            if hasattr(payment, 'custom_invoice_ids') and payment.custom_invoice_ids:
                inv_names = []
                inv_refs = []
                for inv_line in payment.custom_invoice_ids:
                    if inv_line.move_id:
                        inv_names.append(inv_line.move_id.name or '')
                        if inv_line.move_id.ref:
                            inv_refs.append(inv_line.move_id.ref)
                if inv_refs:
                    try:
                        payment.move_id.ref = ', '.join(inv_refs)
                    except Exception:
                        pass

            # 4. Auto-reconcile with invoices from custom_invoice_ids
            if hasattr(payment, 'custom_invoice_ids') and payment.custom_invoice_ids:
                self._auto_reconcile_invoices(payment)

        return res

    def action_draft(self):
        """Override action_draft to unreconcile invoices before resetting to draft"""
        for payment in self:
            # Unreconcile all reconciled lines first
            self._unreconcile_payment(payment)
        # Call super to reset state to draft
        return super().action_draft()

    def _auto_reconcile_invoices(self, payment):
        """Auto-reconcile payment with invoices in custom_invoice_ids
        ใช้ savepoint เพื่อป้องกัน transaction พังถ้า reconcile fail"""
        try:
            with self.env.cr.savepoint():
                # Get payment's receivable/payable move line
                payment_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type in (
                        'asset_receivable', 'liability_payable'
                    ) and not l.reconciled
                )

                if not payment_lines:
                    _logger.warning("No receivable/payable lines for payment %s", payment.name)
                    return

                # Get invoice move lines to reconcile
                invoice_lines = self.env['account.move.line']
                for inv_line in payment.custom_invoice_ids:
                    if inv_line.move_id and inv_line.move_id.state == 'posted':
                        inv_move_lines = inv_line.move_id.line_ids.filtered(
                            lambda l: l.account_id.account_type in (
                                'asset_receivable', 'liability_payable'
                            ) and not l.reconciled
                        )
                        invoice_lines |= inv_move_lines

                if not invoice_lines:
                    _logger.warning("No invoice lines to reconcile for payment %s", payment.name)
                    return

                # Reconcile payment lines with invoice lines
                lines_to_reconcile = payment_lines + invoice_lines
                lines_to_reconcile.reconcile()

                _logger.info("Auto-reconciled payment %s with %d invoices",
                             payment.name, len(payment.custom_invoice_ids))

        except Exception as e:
            _logger.error("Auto-reconcile failed for payment %s: %s", payment.name, str(e))
            self.env.invalidate_all()

        # Force state to 'paid' using SQL (outside savepoint)
        try:
            self.env.cr.execute(
                "UPDATE account_payment SET state = 'paid' WHERE id = %s",
                (payment.id,)
            )
            payment.invalidate_recordset(['state'])
        except Exception as e:
            _logger.error("Set paid state failed: %s", e)

    def _unreconcile_payment(self, payment):
        """Unreconcile payment — invoice goes back to unpaid"""
        try:
            reconciled_lines = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in (
                    'asset_receivable', 'liability_payable'
                ) and l.reconciled
            )
            if reconciled_lines:
                reconciled_lines.remove_move_reconcile()
                _logger.info("Unreconciled payment %s, invoices back to unpaid", payment.name)
        except Exception as e:
            _logger.error("Unreconcile failed for payment %s: %s", payment.name, str(e))

    def action_cancel_payment(self):
        """Cancel payment and reverse reconciliation — invoice goes back to unpaid"""
        for payment in self:
            if payment.state != 'paid':
                raise UserError(_("สามารถยกเลิกได้เฉพาะการชำระเงินที่ชำระแล้ว"))

            # Unreconcile
            self._unreconcile_payment(payment)

            # Cancel the payment move
            payment.move_id.button_draft()
            payment.move_id.button_cancel()
            payment.state = 'canceled'

            _logger.info("Payment %s cancelled, invoices unreconciled", payment.name)
