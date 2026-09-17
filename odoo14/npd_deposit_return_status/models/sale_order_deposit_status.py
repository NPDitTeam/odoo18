# -*- coding: utf-8 -*-
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class SaleOrderDepositStatus(models.Model):
    _inherit = 'sale.order'

    # o18 ประกาศฟิลด์นี้ไว้แล้วใน pfb_npd_all_customs (ไม่มีตัวคำนวณ) ที่นี่ใส่ readonly/copy ตาม o14
    deposit_return_status = fields.Selection([
        ('not_returned', 'ลูกค้ายังไม่คืนสินค้า'),
        ('no_voucher', 'สาขายังไม่สร้างการคืนเงินประกัน'),
        ('waiting_finance', 'รอคืนเงินประกันจากการเงิน'),
        ('done', 'เสร็จสิ้น'),
    ], string='สถานะคืนเงินประกัน', readonly=True, copy=False, tracking=True)

    # =========================================================================
    # Trigger: เมื่อ sale.order.write() เปลี่ยน rental_status
    # → อัปเดต/เคลียร์ deposit_return_status ทันที
    # =========================================================================
    def write(self, vals):
        res = super().write(vals)

        if 'rental_status' in vals:
            for order in self:
                try:
                    if order.pfb_so_type != 'rent':
                        continue
                    # ถ้า deposit เสร็จสิ้นแล้ว ไม่ต้องเคลียร์
                    if order.deposit_return_status == 'done':
                        continue
                    new_status = self._compute_deposit_return_status_for_order(order)
                    if new_status != order.deposit_return_status:
                        # ใช้ super().write เพื่อไม่ให้เรียก trigger วนซ้ำ
                        super(SaleOrderDepositStatus, order).write({'deposit_return_status': new_status})
                        _logger.info("[TRIGGER-SO] %s: rental_status -> %s, deposit -> %s",
                                     order.name, vals['rental_status'], new_status)
                except Exception:
                    _logger.exception("[TRIGGER-SO] Error for %s", order.name)

        return res

    # =========================================================================
    # Scheduled Action (Cron) - สำรอง ทุก 15 นาที
    # =========================================================================
    @api.model
    def run_deposit_return_status_update(self):
        """Scheduled Action: อัปเดตสถานะการคืนเงินประกัน"""
        # ===== ส่วนที่ 1: อัปเดต order ที่ overdue =====
        records = self.search([
            ('rental_status', '=', 'overdue'),
            ('pfb_so_type', '=', 'rent'),
            ('name', 'like', 'SO%'),
        ])
        for order in records:
            try:
                with self.env.cr.savepoint():
                    new_status = self._compute_deposit_return_status_for_order(order)
                    if new_status != order.deposit_return_status:
                        order.sudo().write({'deposit_return_status': new_status})
                        _logger.info("[CRON] %s: deposit -> %s", order.name, new_status)
                        # เมื่อเสร็จสิ้น → อัพเดท rental_status + picking
                        if new_status == 'done':
                            self._on_deposit_done(order)
            except Exception:
                _logger.exception("[CRON] Error processing %s", order.name)

        # ===== ส่วนที่ 2: เคลียร์สถานะที่ค้าง (ไม่ใช่ overdue + ไม่ใช่ done) =====
        stale_records = self.search([
            ('rental_status', '!=', 'overdue'),
            ('deposit_return_status', '!=', False),
            ('deposit_return_status', '!=', 'done'),
            ('pfb_so_type', '=', 'rent'),
        ])
        if stale_records:
            stale_records.sudo().write({'deposit_return_status': False})
            _logger.info("[CRON] Cleared %s stale deposit statuses", len(stale_records))

    # =========================================================================
    # Core Logic - ใช้ร่วมกันทั้ง Cron และ Trigger
    # =========================================================================
    def _compute_deposit_return_status_for_order(self, order):
        """คำนวณสถานะการคืนเงินประกันสำหรับ order เดียว

        1. rental_status ต้อง = 'overdue' ก่อน ถ้าไม่ใช่ → False
        2. stock.picking (picking_type code): outgoing(done) มากกว่า incoming(done) → 'not_returned'
        3. account.voucher (reference = order.name): ไม่พบ → 'no_voucher'
           พบแต่ยังไม่ posted → 'waiting_finance' / posted → 'done'
        """
        if order.rental_status != 'overdue':
            return False

        all_pickings = self.env['stock.picking'].sudo().search([
            ('group_id.name', '=', order.name),
            ('state', '=', 'done'),
        ])
        outgoing_count = len(all_pickings.filtered(lambda p: p.picking_type_id.code == 'outgoing'))
        incoming_count = len(all_pickings.filtered(lambda p: p.picking_type_id.code == 'incoming'))
        if outgoing_count > 0 and outgoing_count > incoming_count:
            return 'not_returned'

        vouchers = self.env['account.voucher'].sudo().search([('reference', '=', order.name)])
        if not vouchers:
            return 'no_voucher'
        if not vouchers.filtered(lambda v: v.state == 'posted'):
            return 'waiting_finance'
        return 'done'

    # =========================================================================
    # Helper: อัปเดตสถานะสำหรับ order เดียว (เรียกจาก trigger ภายนอก)
    # =========================================================================
    def _update_deposit_return_status_single(self):
        for order in self:
            try:
                with self.env.cr.savepoint():
                    new_status = self._compute_deposit_return_status_for_order(order)
                    if new_status != order.deposit_return_status:
                        order.sudo().write({'deposit_return_status': new_status})
                        _logger.info("[TRIGGER] %s: deposit -> %s", order.name, new_status)
                        if new_status == 'done':
                            self._on_deposit_done(order)
            except Exception:
                _logger.exception("[TRIGGER] Error updating %s", order.name)

    def _on_deposit_done(self, order):
        """deposit_return_status = done:
        1. rental_status → 'done' (ปิดบิล) ผ่าน SQL ตรง เพราะเป็น compute+store
           write() ปกติอาจถูกคำนวณทับกลับเป็นสถานะตามวันที่ (เหมือน o14)
        2. ใบรับคืนสินค้า (incoming) ล่าสุด → deposit_return_state = 'returned'
        """
        if order.rental_status != 'done':
            self.env.cr.execute("UPDATE sale_order SET rental_status = %s WHERE id = %s", ('done', order.id))
            order.invalidate_recordset(['rental_status'])
            _logger.info("[DONE] %s: rental_status -> done (via SQL)", order.name)

        last_incoming = self.env['stock.picking'].sudo().search([
            ('group_id.name', '=', order.name),
            ('picking_type_id.code', '=', 'incoming'),
            ('state', '=', 'done'),
        ], order='date_done desc', limit=1)
        if last_incoming and last_incoming.deposit_return_state != 'returned':
            last_incoming.write({'deposit_return_state': 'returned'})
            _logger.info("[DONE] %s: picking %s -> returned", order.name, last_incoming.name)


class StockPickingDepositTrigger(models.Model):
    """Trigger: เมื่อ stock.picking ถูก validate (คืนสินค้า) → อัปเดตสถานะคืนเงินประกันทันที"""
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()
        for picking in self:
            try:
                if picking.group_id and picking.group_id.name:
                    sale_order = self.env['sale.order'].search([
                        ('name', '=', picking.group_id.name),
                        ('rental_status', '=', 'overdue'),
                        ('pfb_so_type', '=', 'rent'),
                    ], limit=1)
                    if sale_order:
                        sale_order._update_deposit_return_status_single()
            except Exception:
                _logger.exception("[TRIGGER-PICKING] Error")
        return res


class AccountVoucherDepositTrigger(models.Model):
    """Trigger: เมื่อ account.voucher ถูก create / write (state/reference) → อัปเดตสถานะทันที"""
    _inherit = 'account.voucher'

    def _trigger_deposit_status_update(self):
        for voucher in self:
            try:
                if voucher.reference:
                    sale_order = self.env['sale.order'].search([
                        ('name', '=', voucher.reference),
                        ('pfb_so_type', '=', 'rent'),
                    ], limit=1)
                    if sale_order:
                        sale_order._update_deposit_return_status_single()
            except Exception:
                _logger.exception("[TRIGGER-VOUCHER] Error")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._trigger_deposit_status_update()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals or 'reference' in vals:
            self._trigger_deposit_status_update()
        return res
