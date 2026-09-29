# -*- coding: utf-8 -*-
"""API รูปโปรไฟล์คนขับ สำหรับแอปขนส่ง

สองปลายทาง
  POST /api/driver/get_image    — ดึงรูปโปรไฟล์ปัจจุบัน
  POST /api/driver/upload_image — อัปโหลด/ลบรูปโปรไฟล์

เขียนลง vehicle.driver.image_1920 ซึ่งเป็นฟิลด์เดียวกับที่หน้า "ผู้ขับขี่"
ใน Odoo ใช้อยู่ รูปจึงซิงก์สองทางโดยไม่ต้องคัดลอกข้อมูลไปไหนอีก

ทำเป็นปลายทางเฉพาะแทนที่จะให้แอปยิง call_kw เขียนตรง เพราะแอปจะได้แก้ได้
เฉพาะรูปของตัวเอง ไม่ใช่ทุกฟิลด์ของทุกคนขับ
"""
import base64
import binascii
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# รูปจากกล้องมือถือใหญ่เกินจำเป็น จำกัดไว้กัน payload บวมและกัน DoS ง่าย ๆ
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class DriverProfileController(http.Controller):

    def _find_driver(self, params):
        """หาคนขับจาก id หรือรหัสพนักงาน — คืน recordset ว่างถ้าไม่เจอ"""
        Driver = request.env['vehicle.driver'].sudo()
        driver_id = params.get('driver_id')
        if driver_id:
            return Driver.browse(int(driver_id)).exists()
        code = (params.get('employee_code') or '').strip()
        if code:
            return Driver.search([('employee_code', '=', code)], limit=1)
        return Driver.browse()

    @http.route('/api/driver/get_image', type='json', auth='public',
                methods=['POST'], csrf=False)
    def get_image(self, **kwargs):
        params = request.get_json_data() if not kwargs else kwargs
        try:
            driver = self._find_driver(params)
            if not driver:
                return {'success': False, 'error': 'ไม่พบคนขับที่ระบุ'}

            # ส่งขนาด 256 ให้แอป พอสำหรับวงกลมโปรไฟล์และเบากว่าต้นฉบับมาก
            image = driver.image_256
            return {
                'success': True,
                'driver_id': driver.id,
                'driver_name': driver.name,
                'has_image': bool(image),
                'image': image.decode() if image else None,
            }
        except Exception as e:
            _logger.exception('[DriverProfile] get_image ล้มเหลว')
            return {'success': False, 'error': str(e)}

    @http.route('/api/driver/upload_image', type='json', auth='public',
                methods=['POST'], csrf=False)
    def upload_image(self, **kwargs):
        params = request.get_json_data() if not kwargs else kwargs
        try:
            driver = self._find_driver(params)
            if not driver:
                return {'success': False, 'error': 'ไม่พบคนขับที่ระบุ'}

            raw = params.get('image')

            # ส่งค่าว่างมา = สั่งลบรูป ไม่ใช่ข้อมูลเสีย
            if not raw:
                driver.write({'image_1920': False})
                _logger.info('[DriverProfile] ลบรูปของ %s', driver.name)
                return {'success': True, 'driver_id': driver.id,
                        'has_image': False, 'image': None}

            if isinstance(raw, bytes):
                raw = raw.decode()
            # แอปบางตัวส่งมาเป็น data URL เต็ม ๆ ตัดหัวออกก่อน
            if raw.startswith('data:'):
                raw = raw.split(',', 1)[-1]

            try:
                decoded = base64.b64decode(raw, validate=True)
            except (binascii.Error, ValueError):
                return {'success': False, 'error': 'รูปภาพไม่ถูกต้อง (base64 เสีย)'}

            if not decoded:
                return {'success': False, 'error': 'ไฟล์รูปว่างเปล่า'}
            if len(decoded) > MAX_IMAGE_BYTES:
                return {'success': False,
                        'error': 'ไฟล์รูปใหญ่เกิน %d MB' % (MAX_IMAGE_BYTES // (1024 * 1024))}

            # Odoo ย่อให้เหลือไม่เกิน 1920px และสร้างขนาดย่อยเองจากฟิลด์นี้
            driver.write({'image_1920': raw})
            driver.invalidate_recordset()
            _logger.info('[DriverProfile] อัปเดตรูปของ %s (%d bytes)',
                         driver.name, len(decoded))

            return {
                'success': True,
                'driver_id': driver.id,
                'has_image': True,
                'image': driver.image_256.decode() if driver.image_256 else None,
            }
        except Exception as e:
            _logger.exception('[DriverProfile] upload_image ล้มเหลว')
            return {'success': False, 'error': str(e)}
