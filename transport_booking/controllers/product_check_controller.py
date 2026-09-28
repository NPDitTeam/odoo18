# -*- coding: utf-8 -*-
"""API ตรวจนับสินค้าสำหรับแอปคนขับ

สองปลายทาง
  POST /api/booking/product_lines  — ดึงรายการสินค้าของใบจอง พร้อมผลตรวจล่าสุด
  POST /api/booking/check_products — บันทึกผลตรวจของคนขับ

ยึดรูปแบบเดิมของแอป (type='json', auth='public') เพื่อให้เรียกได้เหมือน
ปลายทางอื่นที่แอปใช้อยู่แล้ว การยืนยันตัวตนใช้รหัสคนขับเหมือนกัน
"""
import logging

from odoo import fields, http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class ProductCheckController(http.Controller):

    # ------------------------------------------------------------------
    def _find_booking(self, params):
        """หาใบจองจาก id หรือเลขที่จอง — คืน recordset ว่างถ้าไม่เจอ"""
        Booking = request.env['vehicle.booking'].sudo()
        booking_id = params.get('booking_id')
        if booking_id:
            return Booking.browse(int(booking_id)).exists()
        name = (params.get('booking_name') or '').strip()
        if name:
            return Booking.search([('name', '=', name)], limit=1)
        return Booking.browse()

    def _line_payload(self, line):
        return {
            'line_id': line.id,
            'product_name': line.product_name_o14 or '',
            'quantity': line.quantity or 0.0,
            'uom': line.uom_name or '',
            'weight': line.total_weight or 0.0,
            'check_state': line.check_state or 'pending',
            'checked_quantity': line.checked_quantity or 0.0,
            'quantity_diff': line.quantity_diff or 0.0,
            'check_note': line.check_note or '',
            'checked_at': (fields.Datetime.to_string(line.checked_at)
                           if line.checked_at else None),
        }

    def _summary_payload(self, booking):
        return {
            'booking_id': booking.id,
            'booking_name': booking.name,
            'check_state': booking.product_check_state,
            'checked': booking.product_check_done,
            'total': booking.product_check_total,
            'mismatch': booking.product_check_mismatch,
            # แอปใช้ค่านี้ค่าเดียวในการเปิด/ปิดปุ่มกล้อง ไม่ต้องคิดเองซ้ำ
            'can_take_photo': booking.can_take_photo,
        }

    # ------------------------------------------------------------------
    @http.route('/api/booking/product_lines', type='json', auth='public',
                methods=['POST'], csrf=False)
    def get_product_lines(self, **kwargs):
        """รายการสินค้าของใบจอง พร้อมผลตรวจล่าสุด"""
        params = request.get_json_data() if not kwargs else kwargs
        try:
            booking = self._find_booking(params)
            if not booking:
                return {'success': False,
                        'error': 'ไม่พบใบจองที่ระบุ'}
            lines = booking.order_line_ids
            return {
                'success': True,
                'summary': self._summary_payload(booking),
                'lines': [self._line_payload(line) for line in lines],
            }
        except Exception as error:
            _logger.exception('[PRODUCT CHECK] ดึงรายการสินค้าไม่สำเร็จ')
            return {'success': False, 'error': str(error)}

    @http.route('/api/booking/check_products', type='json', auth='public',
                methods=['POST'], csrf=False)
    def save_product_check(self, **kwargs):
        """บันทึกผลตรวจนับของคนขับ

        รับ ``lines`` เป็นรายการของ
            {"line_id": 1, "is_correct": true}
            {"line_id": 2, "is_correct": false, "checked_quantity": 3,
             "note": "ของขาด 1 ชิ้น"}

        เขียนทีละบรรทัดในรอบเดียว ถ้าบรรทัดไหนพัง จะไม่ทำให้ที่เหลือหายไปด้วย
        """
        params = request.get_json_data() if not kwargs else kwargs
        try:
            booking = self._find_booking(params)
            if not booking:
                return {'success': False, 'error': 'ไม่พบใบจองที่ระบุ'}

            driver = booking.driver_id
            driver_id = params.get('driver_id')
            if driver_id:
                found = request.env['vehicle.driver'].sudo().browse(
                    int(driver_id)).exists()
                if found:
                    driver = found

            Line = request.env['transport.order.line'].sudo()
            allowed_ids = set(booking.order_line_ids.ids)
            saved, rejected = 0, []
            for item in (params.get('lines') or []):
                line_id = item.get('line_id')
                if line_id not in allowed_ids:
                    # กันแอปส่ง id ของใบอื่นมาเขียนทับโดยไม่ตั้งใจ
                    rejected.append(line_id)
                    continue
                line = Line.browse(line_id)
                is_correct = bool(item.get('is_correct'))
                line._apply_check(
                    'correct' if is_correct else 'incorrect',
                    checked_quantity=(None if is_correct
                                      else item.get('checked_quantity') or 0.0),
                    note=item.get('note'),
                    driver=driver)
                saved += 1

            booking.invalidate_recordset(
                ['product_check_state', 'product_check_done',
                 'product_check_total', 'product_check_mismatch',
                 'can_take_photo'])
            result = {
                'success': True,
                'saved': saved,
                'summary': self._summary_payload(booking),
            }
            if rejected:
                result['rejected_line_ids'] = rejected
                result['warning'] = 'บางรายการไม่ได้อยู่ในใบจองนี้ จึงไม่ได้บันทึก'
            _logger.info('[PRODUCT CHECK] %s บันทึก %s รายการ สถานะ %s',
                         booking.name, saved, booking.product_check_state)
            return result
        except Exception as error:
            _logger.exception('[PRODUCT CHECK] บันทึกผลตรวจไม่สำเร็จ')
            return {'success': False, 'error': str(error)}
