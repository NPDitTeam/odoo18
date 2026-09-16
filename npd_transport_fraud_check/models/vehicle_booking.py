# -*- coding: utf-8 -*-
"""ดักตอนเที่ยวจัดส่งถูกปิดเป็น "เสร็จสิ้น"

ทั้งหน้าจอ Odoo (ปุ่ม ✔️ เสร็จสิ้น -> wizard -> action_done) และแอปคนขับ
(/api/delivery/complete -> action_done) วิ่งผ่าน action_done() จุดเดียว
จึงดักที่นี่จุดเดียวพอ ครอบคลุมทั้งสองทาง

หลักการ: ห้ามทำให้การปิดงานล้ม — ถ้าตัวตรวจมีปัญหา ให้ปิดงานได้ตามปกติแล้วค่อยบันทึก log
(คนขับอยู่หน้างาน กดปิดงานในแอปแล้วต้องจบ) การเรียก AI ไม่ได้ทำตรงนี้
แต่ตั้งคิวไว้ให้ cron ทำต่อ
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class VehicleBooking(models.Model):
    _inherit = 'vehicle.booking'

    def action_done(self):
        result = super().action_done()
        try:
            with self.env.cr.savepoint():
                self.env['npd.transport.fraud.analyzer'].analyze_bookings(self, force=True)
        except Exception:  # noqa: BLE001 - ตรวจไม่ผ่านต้องไม่ทำให้ปิดงานไม่ได้
            _logger.exception('ตรวจทุจริตการจัดส่ง: ตรวจเที่ยว %s ไม่สำเร็จ', self.ids)
        return result
