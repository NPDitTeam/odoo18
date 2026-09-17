# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

from .cancel_lock_mixin import PARAM_CUTOFF, compute_cutoff, get_lock_day, thai_now

_logger = logging.getLogger(__name__)

# ใบแจ้งหนี้ลูกค้า (รวม Debit Note ที่เป็น out_invoice)
LOCK_MOVE_TYPES = ('out_invoice',)


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'npd.cancel.lock.mixin']

    _cancel_lock_date_field = 'invoice_date'
    _cancel_lock_date_label = 'วันที่ใบแจ้งหนี้'
    _cancel_lock_done_states = ('cancel',)

    @api.model
    def _cancel_lock_scope_domain(self):
        return [('move_type', 'in', LOCK_MOVE_TYPES)]

    def _cancel_lock_in_scope(self):
        return self.move_type in LOCK_MOVE_TYPES

    @api.depends('move_type', 'state', 'invoice_date')
    def _compute_cancel_lock_state(self):
        return super()._compute_cancel_lock_state()

    def _check_cancel_lock(self):
        super()._check_cancel_lock()
        # สมุดรายวันของใบรับชำระ: ทุกทางที่ยกเลิก / รีเซ็ตใบรับชำระ (รวมจากใบคืนเงินประกัน
        # หรือวิซาร์ดต่าง ๆ) สุดท้ายจะมาเรียก button_draft / button_cancel ของ move นี้
        # Odoo 18 ลิงก์ด้วย origin_payment_id / account_payment_invoice ใช้ payment_id
        payments = self.mapped('origin_payment_id')
        if 'payment_id' in self._fields:
            payments |= self.mapped('payment_id')
        payments._check_cancel_lock()

    def button_draft(self):
        self._check_cancel_lock()
        return super().button_draft()

    def button_cancel(self):
        self._check_cancel_lock()
        return super().button_cancel()

    # ------------------------------------------------------------------
    # Scheduled Action
    # ------------------------------------------------------------------
    @api.model
    def _cron_update_cancel_lock(self):
        """ตั้งวันตัดงวดตามวันที่ปัจจุบัน (เวลาไทย) แล้วอัปเดตสถานะใบแจ้งหนี้ / ใบรับชำระ

        รันซ้ำกี่ครั้งก็ได้ผลเท่าเดิม ถ้าเซิร์ฟเวอร์ดับช่วงวันที่ 15
        แล้ว cron มารันทีหลัง ก็ยังได้วันตัดงวดที่ถูกต้อง
        """
        now_th = thai_now()
        cutoff = compute_cutoff(now_th.date(), get_lock_day(self.env))
        self.env['ir.config_parameter'].sudo().set_param(
            PARAM_CUTOFF, fields.Date.to_string(cutoff))
        # ทุกบริษัท (cron รันด้วย superuser แต่ใส่ active_test/บริษัทให้ครบเพื่อความชัวร์)
        moves = self.sudo().with_context(active_test=False)._cancel_lock_refresh(cutoff)
        payments = self.env['account.payment'].sudo().with_context(active_test=False)._cancel_lock_refresh(cutoff)
        _logger.info(
            'npd_cancel_period_lock: เวลาไทย %s วันตัดงวด %s อัปเดตใบแจ้งหนี้ %s ใบ ใบรับชำระ %s ใบ',
            now_th.strftime('%Y-%m-%d %H:%M'), cutoff, moves, payments)
        return cutoff
