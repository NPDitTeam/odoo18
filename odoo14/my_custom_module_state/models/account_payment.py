import logging

from odoo import models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

# วิธีชำระที่ใช้ตอนหักค่าเช่าค้างจากเงินประกัน (ปุ่มรับชำระหนี้ค้างบนใบคืนเงินประกัน)
DEPOSIT_DEDUCT_METHOD = 'หักเงินประกันค่าเช่า'


class AccountPayment(models.Model):
    """อัปเดตสถานะการเช่าทันทีตอนยืนยัน/ยกเลิกใบรับชำระ

    o14 อยู่ใน account_payment_invoice.action_post / ยกเลิก:
    - ชำระครบทุกใบ -> อยู่ระหว่างการเช่า / ใกล้ครบกำหนด / ครบกำหนด
    - รับชำระด้วย "หักเงินประกันค่าเช่า" ครบยอด และรับคืนสินค้าแล้ว -> ปิดบิล (+ ใบรับคืนเป็น "คืนเงินแล้ว")
    - ยกเลิกใบรับชำระแบบหักเงินประกัน -> กลับเป็นอยู่ระหว่างการเช่า (+ ใบรับคืนเป็น "ยังไม่คืนเงิน")
    """
    _inherit = 'account.payment'

    def _npd_rental_orders_of_invoice(self, invoice):
        orders = invoice.invoice_line_ids.sale_line_ids.order_id
        if not orders and invoice.invoice_origin:
            names = [n.strip() for n in invoice.invoice_origin.split(',') if n.strip()]
            orders = self.env['sale.order'].search([('name', 'in', names)])
        return orders.filtered(lambda order: order._npd_rental_automation_applies())

    def _npd_returned_picking(self, order):
        """ใบรับคืนสินค้า (incoming) ที่เสร็จแล้วของใบสั่งเช่า"""
        return self.env['stock.picking'].sudo().search([
            ('group_id.name', '=', order.name),
            ('picking_type_code', '=', 'incoming'),
            ('state', '=', 'done'),
        ], order='date_done desc', limit=1)

    def _npd_is_deposit_deduct(self):
        self.ensure_one()
        return (self.payment_method_one_id.name or '') == DEPOSIT_DEDUCT_METHOD

    def _npd_after_post_rental_status(self):
        self.ensure_one()
        is_deposit = self._npd_is_deposit_deduct()
        orders = self.env['sale.order']
        for inv_line in self.custom_invoice_ids:
            invoice = inv_line.move_id
            if not invoice:
                continue
            invoice_orders = self._npd_rental_orders_of_invoice(invoice)
            orders |= invoice_orders
            if not is_deposit:
                continue
            # o14: amount_due == paid_total (หักจากเงินประกันครบยอด)
            rounding = invoice.currency_id.rounding or 0.01
            if float_compare(inv_line.amount_due, inv_line.paid_total, precision_rounding=rounding) != 0:
                continue
            for order in invoice_orders:
                picking = self._npd_returned_picking(order)
                if not picking or order.rental_status == 'done':
                    continue
                order.sudo().write({'rental_status': 'done', 'check_state': 'done'})
                picking.write({'deposit_return_state': 'returned'})
                _logger.info("ปิดบิล %s จากการหักเงินประกัน %s", order.name, self.name)
        orders._npd_refresh_rental_status()

    def _npd_after_cancel_rental_status(self):
        self.ensure_one()
        if not self._npd_is_deposit_deduct():
            return
        for inv_line in self.custom_invoice_ids:
            if not inv_line.move_id:
                continue
            for order in self._npd_rental_orders_of_invoice(inv_line.move_id):
                picking = self._npd_returned_picking(order)
                if not picking or order.rental_status != 'done':
                    continue
                order.sudo().write({'rental_status': 'in_rent', 'check_state': ''})
                picking.write({'deposit_return_state': 'not_returned'})
                _logger.info("เปิดบิล %s กลับ (ยกเลิกการหักเงินประกัน %s)", order.name, self.name)

    def _npd_run_rental_hook(self, method_name):
        for payment in self:
            try:
                with self.env.cr.savepoint():
                    getattr(payment, method_name)()
            except Exception:
                # สถานะการเช่าเป็นงานเสริม ห้ามทำให้การรับชำระล้ม
                _logger.exception("อัปเดตสถานะการเช่าไม่สำเร็จ (ใบรับชำระ %s)", payment.name)

    def action_post(self):
        res = super().action_post()
        self._npd_run_rental_hook('_npd_after_post_rental_status')
        return res

    def action_cancel_payment(self):
        res = super().action_cancel_payment()
        self._npd_run_rental_hook('_npd_after_cancel_rental_status')
        return res

    def action_draft(self):
        res = super().action_draft()
        self._npd_run_rental_hook('_npd_after_cancel_rental_status')
        return res
