# -*- coding: utf-8 -*-
"""เลขที่ใบรับคืนสินค้าเช่า — ออกให้เฉพาะเที่ยวที่รับของจากลูกค้ากลับเข้าสาขา

เที่ยวประเภท "รับสินค้าจากลูกค้ามายังสาขา" คือการรับของเช่าคืน ซึ่งต้องมีเลข
เอกสารอ้างอิงไว้ผูกกับการคืนของและการคิดค่าเช่า เที่ยวประเภทอื่นไม่ต้องมี
เพราะไม่ได้รับของคืน

ออกเลขตอนกดเสร็จสิ้นเท่านั้น ไม่ใช่ตอนสร้างใบจอง เพราะใบที่ถูกยกเลิกกลางทาง
จะกินเลขไปเปล่า ๆ แล้วเลขเอกสารขาดช่วงโดยไม่มีเหตุผลให้ผู้ตรวจสอบ

รูปแบบเลขแก้ได้เองที่ ตั้งค่า > เทคนิค > ลำดับ (ir.sequence) ชื่อ
"เลขที่ใบรับคืนสินค้าเช่า" ไม่ต้องแก้โค้ด
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

RETURN_SEQUENCE_CODE = 'vehicle.booking.rental.return'


class VehicleBookingRentalReturn(models.Model):
    _inherit = 'vehicle.booking'

    rental_return_number = fields.Char(
        string='เลขที่ใบรับคืนสินค้าเช่า', readonly=True, copy=False, index=True,
        help='ออกอัตโนมัติเมื่อปิดงานของเที่ยวประเภท '
             '"รับสินค้าจากลูกค้ามายังสาขา"\n'
             'แก้รูปแบบเลขได้ที่ ตั้งค่า > เทคนิค > ลำดับ')

    def _needs_rental_return_number(self):
        self.ensure_one()
        return (self.shipment_purpose == 'from_customer'
                and not self.rental_return_number)

    def _assign_rental_return_number(self):
        """ออกเลขให้ใบที่เข้าเงื่อนไข — เรียกซ้ำได้ ไม่ออกเลขซ้ำ"""
        for record in self:
            if not record._needs_rental_return_number():
                continue
            number = record.env['ir.sequence'].sudo().next_by_code(
                RETURN_SEQUENCE_CODE)
            if not number:
                # ลำดับหายไปจากระบบ ไม่ควรทำให้ปิดงานไม่ได้
                _logger.warning(
                    '[RentalReturn] %s: ไม่พบลำดับรหัส %s จึงยังไม่ได้ออกเลข',
                    record.name, RETURN_SEQUENCE_CODE)
                continue
            record.rental_return_number = number
            _logger.info('[RentalReturn] %s: ออกเลขใบรับคืน %s',
                         record.name, number)
            record.message_post(
                body='ออกเลขที่ใบรับคืนสินค้าเช่า: <b>%s</b>' % number)
        return True

    def action_done(self):
        # ออกเลขก่อนปิดงาน เพื่อให้ประวัติการจัดส่งที่สร้างตอน action_done
        # มีเลขติดไปด้วย ถ้าออกทีหลังประวัติจะว่าง
        self._assign_rental_return_number()
        return super().action_done()
