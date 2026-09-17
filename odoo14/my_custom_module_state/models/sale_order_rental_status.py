from datetime import datetime

import pytz

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)

# o14 เช็ค payment_state == 'paid' อย่างเดียว
# o18 มี 'in_payment' = รับชำระแล้วแต่ยังไม่กระทบยอดธนาคาร (o14 ไม่มีสถานะนี้) จึงนับว่าชำระแล้ว
# 'reversed' = ถูกลดหนี้เต็มจำนวนแล้ว ไม่มียอดค้าง
SETTLED_PAYMENT_STATES = ('paid', 'in_payment', 'reversed')


class SaleOrderRentalStatus(models.Model):
    _inherit = 'sale.order'
    _description = 'Custom logic for rental status updates'

    # ------------------------------------------------------------------
    # ตัวช่วย
    # ------------------------------------------------------------------
    @api.model
    def _npd_today_th(self):
        """วันที่ปัจจุบันตามเวลาไทย (cron รันด้วยผู้ใช้ระบบที่ไม่มี timezone ถ้าใช้ UTC
        ช่วง 00:00-07:00 น. จะนับวันผิดไป 1 วัน ทำให้ครบกำหนด/เกินกำหนดเพี้ยน)"""
        return datetime.now(pytz.timezone('Asia/Bangkok')).date()

    def _npd_rental_automation_applies(self):
        """ใช้กับใบสั่งเช่าเท่านั้น และไม่ใช้กับบริษัท เอ็นพีดี โลจิสติกส์
        (o14 ฐานโลจิสติกส์ไม่ได้ติดตั้งระบบสถานะนี้)"""
        self.ensure_one()
        return self.pfb_so_type == 'rent' and not self.is_npd_logistics_company

    def _npd_rental_invoices_settled(self):
        """o14: มีใบแจ้งหนี้ และทุกใบ payment_state = paid (ไม่นับใบที่ยกเลิก)"""
        self.ensure_one()
        invoices = self.invoice_ids.filtered(lambda move: move.state != 'cancel')
        return bool(invoices) and all(
            move.payment_state in SETTLED_PAYMENT_STATES for move in invoices)

    def _npd_rental_days(self, today):
        self.ensure_one()
        rent_days = self.pfb_date_of_rent or 0
        remaining_days = overdue_days = 0
        if self.end_rent_date:
            remaining_days = max((self.end_rent_date - today).days, 0)
            overdue_days = max((today - self.end_rent_date).days, 0)
        return rent_days, remaining_days, overdue_days

    def _npd_next_rental_values(self, today):
        """ค่าที่ต้องเขียนตามกติกา o14 (run_rental_status_update)

        ลำดับความสำคัญ: เกินกำหนด > ครบกำหนด > ใกล้ครบกำหนด > อยู่ระหว่างการเช่า
        เปลี่ยนสถานะเฉพาะใบที่ใบแจ้งหนี้ชำระครบแล้ว (ยังไม่ครบ = คงเป็น "ทำราคา")
        """
        self.ensure_one()
        rent_days, remaining_days, overdue_days = self._npd_rental_days(today)
        values = {}
        if overdue_days <= 300:
            remaining_text = f"{rent_days}/{remaining_days}"
            if self.rent_days_remaining != remaining_text:
                values['rent_days_remaining'] = remaining_text
            if self.rent_days_overdue != overdue_days:
                values['rent_days_overdue'] = overdue_days

        if not self._npd_rental_invoices_settled():
            return values

        # o18 ชื่อรายการราคามีชื่อสาขาต่อท้าย (เช่น "เรทวัน โคราช-บายพาส") o14 ชื่อตรงตัว จึงเช็คแบบมีคำนี้อยู่
        pricelist_name = self.pricelist_id.name or ''
        if overdue_days > 0:
            new_status = 'overdue'
        elif remaining_days == 0:
            new_status = 'due_date'
        elif 'เรทวัน' in pricelist_name:
            new_status = 'nearly_due' if remaining_days == 1 else 'in_rent'
        elif 'เรทเดือน' in pricelist_name:
            new_status = 'nearly_due' if 0 < remaining_days <= 3 else 'in_rent'
        else:
            new_status = 'in_rent'

        if new_status != self.rental_status:
            values['rental_status'] = new_status
        return values

    def _npd_refresh_rental_status(self):
        """อัปเดตสถานะการเช่าทันที (เรียกจาก cron และตอนยืนยัน/ยกเลิกใบรับชำระ)"""
        today = self._npd_today_th()
        changed = self.browse()
        for order in self:
            if order.state in ('draft', 'sent', 'cancel') or order.rental_status == 'done':
                continue
            if not order._npd_rental_automation_applies():
                continue
            values = order._npd_next_rental_values(today)
            if values:
                old_status = order.rental_status
                order.sudo().write(values)
                if 'rental_status' in values:
                    changed |= order
                    _logger.info("สถานะการเช่า %s: %s -> %s", order.name, old_status, values['rental_status'])
        return changed

    # ------------------------------------------------------------------
    # Scheduled actions
    # ------------------------------------------------------------------
    @api.model
    def run_rental_status_update(self):
        """cron ทุก 3 ชม. (o14 "ฟังก์ชันอัปเดต สถานะ ขายเช่า")"""
        records = self.search([
            ('state', 'not in', ('draft', 'sent', 'cancel')),
            ('pfb_so_type', '=', 'rent'),
            ('name', 'like', 'SO%'),
            ('rental_status', '!=', 'done'),
        ])
        _logger.info("อัปเดตสถานะการเช่า: ตรวจ %s ใบ", len(records))
        changed = 0
        for order in records:
            try:
                with self.env.cr.savepoint():
                    changed += len(order._npd_refresh_rental_status())
            except Exception:
                _logger.exception("อัปเดตสถานะการเช่าไม่สำเร็จ: %s", order.name)
        _logger.info("อัปเดตสถานะการเช่า: เปลี่ยนสถานะ %s ใบ", changed)
        return changed

    @api.model
    def run_rental_status_overdue_update(self):
        """cron รายวัน (o14 custom_function_update_overdue): เลยวันสิ้นสุดเช่า = เกินกำหนด
        ตั้งให้ใบที่ยืนยันแล้วทุกใบ แม้ใบแจ้งหนี้ยังชำระไม่ครบ"""
        today = self._npd_today_th()
        records = self.search([
            ('state', 'not in', ('draft', 'sent', 'cancel')),
            ('pfb_so_type', '=', 'rent'),
            ('name', 'like', 'SO%'),
            ('rental_status', 'not in', ('overdue', 'done')),
            ('end_rent_date', '<', today),
        ])
        count = 0
        for order in records:
            if not order._npd_rental_automation_applies():
                continue
            try:
                with self.env.cr.savepoint():
                    order.sudo().write({'rental_status': 'overdue'})
                    count += 1
            except Exception:
                _logger.exception("ตั้งสถานะเกินกำหนดไม่สำเร็จ: %s", order.name)
        _logger.info("อัปเดตสถานะเกินกำหนด: %s ใบ", count)
        return count
