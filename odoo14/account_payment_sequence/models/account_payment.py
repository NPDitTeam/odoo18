from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # ต้องประกาศ depends เดิมซ้ำ เพราะ override ไปแทนที่ method ใน MRO
    @api.depends('payment_type')
    def _compute_available_journal_ids(self):
        """เปิดให้เลือกสมุดรายวัน รับชำระ/จ่ายชำระ ได้เหมือน Odoo 14

        Odoo 18 ฮาร์ดโค้ด type in ('bank','cash','credit') ไว้ ทำให้เลือก
        สมุดรายวันรับชำระไม่ได้ ส่วน Odoo 14 โมดูลนี้ override domain ของ
        journal_id เป็น [('type','in',('receivable','payable'))] ไว้

        ยังต้องมี payment_method_line อยู่จริง ไม่งั้นช่องวิธีการชำระเงิน
        (required) จะว่างและบันทึกไม่ได้ — ดู account_journal.py ในโมดูลนี้
        """
        super()._compute_available_journal_ids()

        extra_journals = self.env['account.journal'].search([
            '|',
            ('company_id', 'parent_of', self.env.company.id),
            ('company_id', 'child_of', self.env.company.id),
            ('type', 'in', ('receivable', 'payable')),
        ])
        for pay in self:
            if pay.payment_type == 'inbound':
                extra = extra_journals.filtered('inbound_payment_method_line_ids')
            else:
                extra = extra_journals.filtered('outbound_payment_method_line_ids')
            pay.available_journal_ids = pay.available_journal_ids | extra

    # ------------------------------------------------------------------
    # เลขที่ใบรับ/จ่ายชำระ แบบ Odoo 14
    #
    # o14: ใบรับชำระ = CUST.IN-260915-0013 (sequence customer.payment)
    #      รายการบันทึกบัญชี = RV-2609150008 (sequence ของสมุดรายวัน)
    # o18 เดิมคัดลอกเลขรายการบันทึกบัญชีมาเป็นเลขใบรับชำระ (_compute_name ของ Odoo)
    # แล้วโมดูลนี้ยังเขียน CUST.IN ทับเลขรายการบันทึกบัญชีด้วย SQL ทั้งสองเลขจึงกลายเป็นเลขเดียวกัน
    # ตอนนี้แยกกันเหมือน o14: เลขรายการบันทึกบัญชีปล่อยให้ psn_journal_sequence ออกตามสมุดรายวัน
    # เลขใบรับชำระออกจาก sequence ของบริษัทนั้น ตามวันที่ของใบ (ไม่ใช่วันที่กดยืนยัน)
    # ------------------------------------------------------------------
    npd_number_assigned = fields.Boolean(
        string='ออกเลขใบรับ/จ่ายชำระแล้ว',
        copy=False,
        help='ออกเลขจาก sequence customer.payment / supplier.payment แล้ว '
             'เลขนี้จะไม่ถูกเปลี่ยนตามเลขรายการบันทึกบัญชีอีก และกลับเป็นร่างแล้วยืนยันใหม่ก็ใช้เลขเดิม',
    )

    # ต้องประกาศ depends เดิมซ้ำ เพราะ override ไปแทนที่ method ใน MRO
    @api.depends('move_id.name', 'state')
    def _compute_name(self):
        assigned = self.filtered('npd_number_assigned')
        for payment in assigned:
            payment.name = payment.name
        others = self - assigned
        if others:
            super(AccountPayment, others)._compute_name()

    def get_seq_payment(self):
        """เลขถัดไปของ customer.payment / supplier.payment ของบริษัทใบนี้ ตามวันที่ของใบ

        ฐานเดียวหลายบริษัท: next_by_code เลือก sequence ของบริษัทที่อยู่ใน env ก่อน
        (o14 แยกฐานละบริษัท เลขของแต่ละบริษัทจึงไม่ปนกัน)
        """
        self.ensure_one()
        code = 'customer.payment' if self.payment_type == 'inbound' else 'supplier.payment'
        return self.env['ir.sequence'].with_company(self.company_id).next_by_code(
            code, sequence_date=self.date) or '/'

    def _npd_assign_payment_number(self):
        for payment in self:
            if payment.npd_number_assigned or payment.state not in ('in_process', 'paid'):
                continue
            number = payment.get_seq_payment()
            if number and number != '/':
                payment.write({'name': number, 'npd_number_assigned': True})

    def action_post(self):
        """ออกเลขใบรับ/จ่ายชำระ + ใส่หมายเหตุจากใบแจ้งหนี้ + กระทบยอดกับใบแจ้งหนี้"""
        res = super().action_post()
        self._npd_assign_payment_number()
        for payment in self:
            if not payment.move_id:
                continue

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
