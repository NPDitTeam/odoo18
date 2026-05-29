from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
from datetime import datetime, date
import pytz

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cancel_summary = fields.Text(string="สรุปรายการยกเลิก")

    def copy(self, default=None):
        default = dict(default or {})
        default['cancel_summary'] = ""
        return super().copy(default)

    def action_open_cancel_wizard(self):
        """เช็คสิทธิ์ก่อนเปิด Wizard"""
        if not self.env.user.cancel_rent_same_day:
            if self.date_order:
                order_date = self.date_order.date() if isinstance(self.date_order, datetime) else self.date_order
                today = date.today()
                if order_date != today:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('ไม่สามารถยกเลิกได้'),
                            'message': _('คุณสามารถยกเลิกได้เฉพาะในวันที่สั่งเช่าเท่านั้น'),
                            'type': 'danger',
                        }
                    }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('ไม่สามารถยกเลิกได้'),
                        'message': _('ไม่พบวันที่สั่งเช่า'),
                        'type': 'danger',
                    }
                }

        return {
            'name': 'ยกเลิกรายการอ้างอิงบิลเช่า',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sale_id': self.id},
        }


class SaleOrderCancelWizard(models.TransientModel):
    _name = 'sale.order.cancel.wizard'
    _description = 'Cancel Related Documents Wizard'

    sale_id = fields.Many2one('sale.order', required=True)
    cancel_sale_order = fields.Boolean("ยกเลิกใบเช่า")
    cancel_invoice = fields.Boolean("ยกเลิกใบแจ้งหนี้")
    cancel_delivery = fields.Boolean("ยกเลิกใบจัดส่งสินค้า")
    cancel_stock_cut = fields.Boolean("ยกเลิกการตัดสต๊อกสินค้า")
    cancel_insurance = fields.Boolean("ยกเลิกใบแจ้งหนี้รับเงินประกัน")
    cancel_payment = fields.Boolean("ยกเลิกใบรับชำระเงิน")
    cancel_debit_note = fields.Boolean("ยกเลิก Debit Note")
    select_all = fields.Boolean("เลือกทั้งหมด")
    cancel_summary = fields.Text(
        string="สรุปรายการยกเลิก",
        related='sale_id.cancel_summary',
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'default_sale_id' in self.env.context:
            sale = self.env['sale.order'].browse(self.env.context['default_sale_id'])
            res['cancel_summary'] = sale.cancel_summary
        return res

    @api.onchange('select_all')
    def _onchange_select_all(self):
        if self.select_all:
            self.cancel_sale_order = True
            self.cancel_invoice = True
            self.cancel_delivery = True
            self.cancel_stock_cut = True
            self.cancel_insurance = True
            self.cancel_payment = True
            self.cancel_debit_note = True
        else:
            self.cancel_sale_order = False
            self.cancel_invoice = False
            self.cancel_delivery = False
            self.cancel_stock_cut = False
            self.cancel_insurance = False
            self.cancel_payment = False
            self.cancel_debit_note = False

    @api.onchange('cancel_sale_order')
    def _onchange_cancel_sale_order(self):
        if self.cancel_sale_order:
            self.cancel_invoice = True
            self.cancel_delivery = True
            self.cancel_stock_cut = True
            self.cancel_insurance = True
            self.cancel_payment = True
            self.cancel_debit_note = True

    @api.onchange('cancel_invoice', 'cancel_delivery', 'cancel_stock_cut', 'cancel_insurance',
                  'cancel_payment', 'cancel_debit_note')
    def _onchange_cancel_options(self):
        all_selected = (self.cancel_sale_order and self.cancel_invoice and
                        self.cancel_delivery and self.cancel_stock_cut and
                        self.cancel_insurance and self.cancel_payment and
                        self.cancel_debit_note)
        if all_selected:
            self.select_all = True
        else:
            self.select_all = False

    def _is_return_picking(self, picking):
        # Odoo 18: move_ids แทน move_lines
        return any(m.origin_returned_move_id for m in picking.move_ids)

    def _has_been_returned(self, picking):
        for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
            returned_done = move.returned_move_ids.filtered(lambda rm: rm.state == 'done')
            if returned_done:
                return True
        return False

    def _handle_stock_return(self, picking, tz):
        messages = []
        now_thai = datetime.now(tz)

        if picking.state == 'done':
            picking_type = picking.picking_type_id.code if picking.picking_type_id else 'N/A'
            has_returned = self._has_been_returned(picking)

            if picking_type == 'incoming':
                messages.append(
                    "ข้าม %s (เป็นใบรับสินค้าเข้า ไม่ต้องคืนซ้ำ) (%s)" %
                    (picking.name, now_thai.strftime('%d/%m/%Y %H:%M:%S'))
                )
                return messages

            if has_returned:
                messages.append(
                    "ข้าม %s (คืนสต๊อกไปแล้วก่อนหน้านี้) (%s)" %
                    (picking.name, now_thai.strftime('%d/%m/%Y %H:%M:%S'))
                )
                return messages

            # Odoo 18: move_ids แทน move_lines, quantity แทน quantity_done
            done_moves = picking.move_ids.filtered(lambda m: m.state == 'done' and m.quantity > 0)
            if done_moves:
                try:
                    return_wiz = self.env['stock.return.picking'].with_context(active_id=picking.id).create({
                        'picking_id': picking.id,
                        'location_id': picking.location_id.id,
                        'product_return_moves': [(0, 0, {
                            'product_id': move.product_id.id,
                            'quantity': move.quantity,
                            'move_id': move.id,
                        }) for move in done_moves],
                    })

                    return_action = return_wiz.create_returns()
                    return_pick_id = return_action.get('res_id')

                    if return_pick_id:
                        return_pick = self.env['stock.picking'].browse(return_pick_id)
                        return_pick.action_confirm()
                        return_pick.action_assign()

                        # Odoo 18: quantity แทน quantity_done
                        for move in return_pick.move_ids:
                            move.quantity = move.product_uom_qty

                        for sml in return_pick.move_line_ids:
                            if sml.quantity == 0:
                                sml.quantity = sml.quantity_product_uom

                        validate_result = return_pick.sudo().button_validate()

                        if isinstance(validate_result, dict) and validate_result.get('res_model'):
                            wizard_model = validate_result.get('res_model')
                            if wizard_model == 'stock.immediate.transfer':
                                immediate_wiz = self.env['stock.immediate.transfer'].create({
                                    'pick_ids': [(6, 0, [return_pick.id])],
                                })
                                immediate_wiz.process()
                            elif wizard_model == 'stock.backorder.confirmation':
                                backorder_wiz = self.env['stock.backorder.confirmation'].create({
                                    'pick_ids': [(6, 0, [return_pick.id])],
                                })
                                backorder_wiz.process()

                        return_pick.invalidate_recordset()

                        if return_pick.state == 'done':
                            messages.append(
                                "คืนสต๊อก %s เรียบร้อย (คืน %d รายการ) (%s)" %
                                (picking.name, len(done_moves), now_thai.strftime('%d/%m/%Y %H:%M:%S'))
                            )
                        else:
                            messages.append(
                                "คืนสต๊อก %s สร้างใบคืนแล้ว (%s) แต่สถานะ: %s (%s)" %
                                (picking.name, return_pick.name, return_pick.state, now_thai.strftime('%d/%m/%Y %H:%M:%S'))
                            )
                except Exception as e:
                    _logger.error("Error returning stock for picking %s: %s", picking.name, str(e))
                    messages.append("ไม่สามารถคืนสต๊อก %s: %s" % (picking.name, str(e)))
        elif picking.state not in ['cancel']:
            picking.action_cancel()
            messages.append(
                "ยกเลิก %s ที่รอดำเนินการ (%s)" %
                (picking.name, now_thai.strftime('%d/%m/%Y %H:%M:%S'))
            )

        return messages

    def confirm_cancel(self):
        selected_items = []
        if self.cancel_sale_order: selected_items.append("ใบเช่า")
        if self.cancel_invoice: selected_items.append("ใบแจ้งหนี้")
        if self.cancel_delivery: selected_items.append("ใบจัดส่งสินค้า")
        if self.cancel_stock_cut: selected_items.append("การตัดสต๊อกสินค้า")
        if self.cancel_insurance: selected_items.append("ใบแจ้งหนี้รับเงินประกัน")
        if self.cancel_payment: selected_items.append("ใบรับชำระเงิน")
        if self.cancel_debit_note: selected_items.append("Debit Note")

        if not selected_items:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('กรุณาเลือกรายการ'),
                    'message': _('กรุณาเลือกรายการที่ต้องการยกเลิกอย่างน้อย 1 รายการ'),
                    'type': 'warning',
                }
            }

        messages = []
        tz = pytz.timezone('Asia/Bangkok')

        invoice_names = [inv.name for inv in self.sale_id.invoice_ids if inv.name]
        if hasattr(self.sale_id, 'rent_check'):
            for inv in self.sale_id.rent_check:
                if inv.name and inv.name not in invoice_names:
                    invoice_names.append(inv.name)
        so_name = self.sale_id.name
        all_moves_by_so = self.env['account.move'].sudo().search([
            ('invoice_origin', '=', so_name),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('id', 'not in', self.sale_id.invoice_ids.ids),
        ])
        for mv in all_moves_by_so:
            if mv.name and mv.name not in invoice_names:
                invoice_names.append(mv.name)

        try:
            self.env.cr.execute("SAVEPOINT cancel_operation")

            # ยกเลิกใบเช่า
            if self.cancel_sale_order:
                now_thai = datetime.now(tz)
                stock_messages = []
                for picking in self.sale_id.picking_ids:
                    stock_msg = self._handle_stock_return(picking, tz)
                    stock_messages.extend(stock_msg)

                if self.sale_id.state not in ['cancel', 'done']:
                    try:
                        self.env.cr.execute("""
                            UPDATE sale_order SET state = 'cancel' WHERE id = %s
                        """, (self.sale_id.id,))
                        self.sale_id.invalidate_recordset(['state'])
                        messages.append("ยกเลิกใบเช่า %s เรียบร้อย (%s)" %
                                        (self.sale_id.name, now_thai.strftime('%d/%m/%Y %H:%M:%S')))
                        if stock_messages:
                            messages.append("  การจัดการสต๊อก:")
                            for msg in stock_messages:
                                messages.append("     " + msg)
                    except Exception as e:
                        messages.append("ไม่สามารถยกเลิกใบเช่า %s: %s" % (self.sale_id.name, str(e)))
                elif self.sale_id.state == 'done':
                    messages.append("ใบเช่า %s อยู่ในสถานะ done ไม่สามารถยกเลิกได้" % self.sale_id.name)
                else:
                    messages.append("ใบเช่ายกเลิกไปแล้วก่อนหน้านี้")

            # ยกเลิกใบแจ้งหนี้
            if self.cancel_invoice:
                now_thai = datetime.now(tz)
                cancelled_invoices = []
                for invoice in self.sale_id.invoice_ids:
                    if invoice.state != 'cancel':
                        try:
                            self.env.cr.execute("SAVEPOINT cancel_invoice_op")
                            inv = invoice.sudo()
                            if inv.state == 'posted':
                                reconciled_lines = inv.line_ids.filtered(
                                    lambda l: l.account_id.reconcile and l.reconciled
                                )
                                if reconciled_lines:
                                    reconciled_lines.remove_move_reconcile()
                                inv.mapped('line_ids.analytic_line_ids').unlink()
                                inv.write({'state': 'draft', 'is_move_sent': False})
                            inv.write({'auto_post': 'no', 'state': 'cancel'})
                            self.env.cr.execute("RELEASE SAVEPOINT cancel_invoice_op")
                            cancelled_invoices.append(invoice.name or str(invoice.id))
                        except Exception as e:
                            self.env.cr.execute("ROLLBACK TO SAVEPOINT cancel_invoice_op")
                            messages.append("ไม่สามารถยกเลิกใบแจ้งหนี้ %s: %s" % (invoice.name, str(e)))

                if cancelled_invoices:
                    messages.append("ยกเลิกใบแจ้งหนี้ %d ใบ (%s)" %
                                    (len(cancelled_invoices), now_thai.strftime('%d/%m/%Y %H:%M:%S')))

            # ยกเลิกใบจัดส่งสินค้า
            if self.cancel_delivery and not self.cancel_sale_order:
                now_thai = datetime.now(tz)
                for picking in self.sale_id.picking_ids:
                    if picking.state not in ['cancel', 'done']:
                        try:
                            self.env.cr.execute("SAVEPOINT cancel_delivery_op")
                            picking.sudo().action_cancel()
                            self.env.cr.execute("RELEASE SAVEPOINT cancel_delivery_op")
                            messages.append("ยกเลิก %s เรียบร้อย (%s)" %
                                            (picking.name, now_thai.strftime('%d/%m/%Y %H:%M:%S')))
                        except Exception as e:
                            self.env.cr.execute("ROLLBACK TO SAVEPOINT cancel_delivery_op")
                            messages.append("ไม่สามารถยกเลิกใบจัดส่ง %s: %s" % (picking.name, str(e)))

            # ยกเลิกการตัดสต๊อก
            if self.cancel_stock_cut and not self.cancel_sale_order:
                now_thai = datetime.now(tz)
                done_pickings = self.sale_id.picking_ids.filtered(lambda p: p.state == 'done')
                if done_pickings:
                    for picking in done_pickings:
                        stock_msg = self._handle_stock_return(picking, tz)
                        messages.extend(stock_msg)
                else:
                    messages.append("ไม่พบรายการตัดสต็อกที่ต้องคืน")

            # ยกเลิกใบรับเงินประกัน
            if self.cancel_insurance:
                now_thai = datetime.now(tz)
                cancelled_insurance = []
                if hasattr(self.sale_id, 'rent_check'):
                    for inv in self.sale_id.rent_check:
                        if inv.state != 'cancel':
                            try:
                                self.env.cr.execute("SAVEPOINT cancel_insurance_op")
                                ins = inv.sudo()
                                if ins.state == 'posted':
                                    reconciled_lines = ins.line_ids.filtered(
                                        lambda l: l.account_id.reconcile and l.reconciled
                                    )
                                    if reconciled_lines:
                                        reconciled_lines.remove_move_reconcile()
                                    ins.mapped('line_ids.analytic_line_ids').unlink()
                                    ins.write({'state': 'draft', 'is_move_sent': False})
                                ins.write({'auto_post': 'no', 'state': 'cancel'})
                                self.env.cr.execute("RELEASE SAVEPOINT cancel_insurance_op")
                                cancelled_insurance.append(inv.name or str(inv.id))
                            except Exception as e:
                                self.env.cr.execute("ROLLBACK TO SAVEPOINT cancel_insurance_op")
                                messages.append("ไม่สามารถยกเลิกใบรับเงินประกัน %s: %s" % (inv.name, str(e)))

                    if cancelled_insurance:
                        messages.append("ยกเลิกใบรับเงินประกัน %d ใบ (%s)" %
                                        (len(cancelled_insurance), now_thai.strftime('%d/%m/%Y %H:%M:%S')))

            # ยกเลิกใบรับชำระเงิน
            if self.cancel_payment:
                now_thai = datetime.now(tz)
                AccountPayment = self.env['account.payment'].sudo()
                found_payments = AccountPayment

                for inv_name in invoice_names:
                    if hasattr(AccountPayment, 'search_invoice_name'):
                        pays = AccountPayment.search([
                            ('search_invoice_name', '=', inv_name),
                            ('state', '!=', 'cancel'),
                        ])
                        found_payments |= pays

                all_invoices = self.sale_id.invoice_ids
                if hasattr(self.sale_id, 'rent_check'):
                    all_invoices |= self.sale_id.rent_check
                if all_invoices and 'account.payment.invoice' in self.env:
                    PaymentInvoice = self.env['account.payment.invoice'].sudo()
                    pay_inv_lines = PaymentInvoice.search([('invoice_id', 'in', all_invoices.ids)])
                    for pi in pay_inv_lines:
                        if pi.payment_id and pi.payment_id.state != 'cancel':
                            found_payments |= pi.payment_id

                cancelled_payments = []
                for pay in found_payments:
                    try:
                        self.env.cr.execute("SAVEPOINT cancel_payment_op")
                        payment_move = pay.move_id
                        if pay.state == 'posted':
                            reconciled_lines = payment_move.line_ids.filtered(
                                lambda l: l.account_id.reconcile and l.reconciled
                            )
                            if reconciled_lines:
                                reconciled_lines.remove_move_reconcile()
                            payment_move.mapped('line_ids.analytic_line_ids').unlink()
                            payment_move.write({'state': 'draft', 'is_move_sent': False})
                        payment_move.write({'auto_post': 'no', 'state': 'cancel'})
                        self.env.cr.execute("RELEASE SAVEPOINT cancel_payment_op")
                        cancelled_payments.append(pay.name or str(pay.id))
                    except Exception as e:
                        try:
                            self.env.cr.execute("ROLLBACK TO SAVEPOINT cancel_payment_op")
                        except Exception:
                            pass
                        messages.append("ไม่สามารถยกเลิกใบรับชำระเงิน %s: %s" % (pay.name, str(e)))

                if cancelled_payments:
                    messages.append("ยกเลิกใบรับชำระเงิน %d ใบ (%s)" %
                                    (len(cancelled_payments), now_thai.strftime('%d/%m/%Y %H:%M:%S')))

            # ยกเลิก Debit Note
            if self.cancel_debit_note:
                now_thai = datetime.now(tz)
                cancelled_debit_notes = []
                so_name = self.sale_id.name
                existing_inv_ids = self.sale_id.invoice_ids.ids
                all_debit_notes = self.env['account.move'].sudo().search([
                    ('invoice_origin', '=', so_name),
                    ('move_type', 'in', ['out_invoice', 'out_refund']),
                    ('id', 'not in', existing_inv_ids),
                    ('state', '!=', 'cancel'),
                ])

                for dn in all_debit_notes:
                    try:
                        self.env.cr.execute("SAVEPOINT cancel_debit_note_op")
                        if dn.state == 'posted':
                            reconciled_lines = dn.line_ids.filtered(
                                lambda l: l.account_id.reconcile and l.reconciled
                            )
                            if reconciled_lines:
                                reconciled_lines.remove_move_reconcile()
                            dn.mapped('line_ids.analytic_line_ids').unlink()
                            dn.write({'state': 'draft', 'is_move_sent': False})
                        dn.write({'auto_post': 'no', 'state': 'cancel'})
                        self.env.cr.execute("RELEASE SAVEPOINT cancel_debit_note_op")
                        cancelled_debit_notes.append(dn.name or str(dn.id))
                    except Exception as e:
                        try:
                            self.env.cr.execute("ROLLBACK TO SAVEPOINT cancel_debit_note_op")
                        except Exception:
                            pass
                        messages.append("ไม่สามารถยกเลิก Debit Note %s: %s" % (dn.name, str(e)))

                if cancelled_debit_notes:
                    messages.append("ยกเลิก Debit Note %d ใบ (%s)" %
                                    (len(cancelled_debit_notes), now_thai.strftime('%d/%m/%Y %H:%M:%S')))

                # ยกเลิก payment ที่เกี่ยวกับ debit note
                dn_names = [dn.name for dn in all_debit_notes if dn.name]
                if dn_names:
                    AccountPayment = self.env['account.payment'].sudo()
                    dn_payments = AccountPayment
                    for dn_name in dn_names:
                        if hasattr(AccountPayment, 'search_invoice_name'):
                            pays = AccountPayment.search([
                                ('search_invoice_name', '=', dn_name),
                                ('state', '!=', 'cancel'),
                            ])
                            dn_payments |= pays

                    if 'account.payment.invoice' in self.env:
                        PaymentInvoice = self.env['account.payment.invoice'].sudo()
                        pi_lines = PaymentInvoice.search([('invoice_id', 'in', all_debit_notes.ids)])
                        for pi in pi_lines:
                            if pi.payment_id and pi.payment_id.state != 'cancel':
                                dn_payments |= pi.payment_id

                    cancelled_dn_payments = []
                    for pay in dn_payments:
                        try:
                            self.env.cr.execute("SAVEPOINT cancel_dn_payment_op")
                            payment_move = pay.move_id
                            if pay.state == 'posted':
                                reconciled_lines = payment_move.line_ids.filtered(
                                    lambda l: l.account_id.reconcile and l.reconciled
                                )
                                if reconciled_lines:
                                    reconciled_lines.remove_move_reconcile()
                                payment_move.mapped('line_ids.analytic_line_ids').unlink()
                                payment_move.write({'state': 'draft', 'is_move_sent': False})
                            payment_move.write({'auto_post': 'no', 'state': 'cancel'})
                            self.env.cr.execute("RELEASE SAVEPOINT cancel_dn_payment_op")
                            cancelled_dn_payments.append(pay.name or str(pay.id))
                        except Exception as e:
                            try:
                                self.env.cr.execute("ROLLBACK TO SAVEPOINT cancel_dn_payment_op")
                            except Exception:
                                pass

                    if cancelled_dn_payments:
                        messages.append("ยกเลิกใบรับชำระ Debit Note %d ใบ (%s)" %
                                        (len(cancelled_dn_payments), now_thai.strftime('%d/%m/%Y %H:%M:%S')))

            # อัปเดตสรุปสถานะ
            summary_text = "\n".join(messages) if messages else "ไม่มีรายการที่ถูกยกเลิก"
            if summary_text:
                existing_summary = self.sale_id.cancel_summary or ""
                if existing_summary:
                    new_summary = existing_summary + "\n\n--- อัปเดตล่าสุด ---\n" + summary_text
                else:
                    new_summary = summary_text
                self.env.cr.execute("""
                    UPDATE sale_order SET cancel_summary = %s WHERE id = %s
                """, (new_summary, self.sale_id.id))

            self.env.cr.execute("RELEASE SAVEPOINT cancel_operation")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('ยกเลิกเรียบร้อย'),
                    'message': _('ดำเนินการยกเลิกรายการที่เลือกเรียบร้อยแล้ว'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            try:
                self.env.cr.execute("ROLLBACK TO SAVEPOINT cancel_operation")
            except Exception:
                pass
            _logger.error("Error in cancel operation: %s", str(e))
            raise UserError(_("เกิดข้อผิดพลาดในการยกเลิก: %s") % str(e))
