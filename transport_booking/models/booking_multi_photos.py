# -*- coding: utf-8 -*-
"""รับรูปได้หลายรูปต่อหนึ่งเที่ยว ทั้งตอนเริ่มงานและตอนส่งถึง

ฟิลด์เดิม pickup_photo และ delivery_photo เป็น Binary เก็บได้รูปเดียว
ของจริงคนขับต้องถ่ายหลายมุม โดยเฉพาะตอนของขาดหรือมีรอยเสียหาย รูปเดียว
เถียงกันไม่จบว่าของครบตอนออกจากคลังหรือเปล่า

เก็บเพิ่มเป็น Many2many ของ ir.attachment แต่ยังเขียนรูปแรกลงฟิลด์ Binary
เดิมด้วย เพราะหน้าจอ ประวัติการจัดส่ง และรายงานที่มีอยู่อ่านจากฟิลด์นั้น
ถ้าเลิกเขียนจะพังเงียบ ๆ ทั้งที่ข้อมูลยังอยู่
"""
import base64
import binascii
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_PHOTOS = 10


class VehicleBookingMultiPhotos(models.Model):
    _inherit = 'vehicle.booking'

    delivery_photo_ids = fields.Many2many(
        'ir.attachment',
        'vehicle_booking_delivery_photo_rel', 'booking_id', 'attachment_id',
        string='รูปหลักฐานการส่ง', copy=False)
    delivery_photo_count = fields.Integer(
        string='จำนวนรูปหลักฐานการส่ง',
        compute='_compute_delivery_photo_count')

    @api.depends('delivery_photo_ids')
    def _compute_delivery_photo_count(self):
        for record in self:
            record.delivery_photo_count = len(record.delivery_photo_ids)

    # ------------------------------------------------------------------
    def _npd_store_photos(self, field_name, photos, label):
        """แปลง base64 หลายรูปเป็น ir.attachment แล้วผูกกับใบจอง

        คืนจำนวนรูปที่เก็บได้จริง รูปที่เสียจะถูกข้ามพร้อมเขียน log ไม่ทำให้
        ทั้งคำขอล้ม เพราะคนขับกดจบงานแล้วเน็ตหลุดกลางทางเป็นเรื่องปกติ
        การเสียรูปหนึ่งใบไม่ควรทำให้ปิดงานไม่ได้
        """
        self.ensure_one()
        if not photos:
            return 0

        attachments = self.env['ir.attachment'].sudo()
        created = attachments.browse()
        for index, raw in enumerate(photos[:MAX_PHOTOS], start=1):
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode()
            if raw.startswith('data:'):
                raw = raw.split(',', 1)[-1]
            try:
                decoded = base64.b64decode(raw, validate=True)
            except (binascii.Error, ValueError):
                _logger.warning('[MultiPhotos] %s: รูปที่ %d เป็น base64 เสีย ข้ามไป',
                                self.name, index)
                continue
            if not decoded or len(decoded) > MAX_PHOTO_BYTES:
                _logger.warning('[MultiPhotos] %s: รูปที่ %d ขนาดไม่ผ่าน (%d bytes) ข้ามไป',
                                self.name, index, len(decoded))
                continue
            created |= attachments.create({
                'name': '%s-%s-%02d.jpg' % (self.name or 'BOOKING', label, index),
                'datas': raw,
                'res_model': 'vehicle.booking',
                'res_id': self.id,
                'mimetype': 'image/jpeg',
            })

        if created:
            self.write({field_name: [(4, a.id) for a in created]})
            _logger.info('[MultiPhotos] %s: เก็บรูป %s %d ใบ',
                         self.name, label, len(created))
        return len(created)

    # ------------------------------------------------------------------
    def start_job_with_photo(self, photo_base64, extra_photos=None,
                             driver_latitude=None, driver_longitude=None):
        """เริ่มงานพร้อมรูป — รองรับหลายรูปผ่าน extra_photos

        คงพารามิเตอร์ตัวแรกไว้เหมือนเดิม เพราะแอปรุ่นเก่าที่ยังไม่อัปเดต
        เรียกแบบตำแหน่งเดียวอยู่ ถ้าเปลี่ยนลายเซ็นจะพังทันทีตอนคนขับกดเริ่มงาน
        """
        res = super().start_job_with_photo(
            photo_base64,
            driver_latitude=driver_latitude,
            driver_longitude=driver_longitude,
        )
        photos = [photo_base64] + list(extra_photos or [])
        self._npd_store_photos('start_check_photo_ids', photos, 'ก่อนขนส่ง')
        return res
