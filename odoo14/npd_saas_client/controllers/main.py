# -*- coding: utf-8 -*-
"""บังคับใช้สัญญากับ REST API ของแอป HR

ต่อยอดจาก ``HrmsApiController`` โดยแทรกการตรวจสัญญาไว้ที่ ``_current_employee``
ซึ่งเป็นทางผ่านของ *ทุก* endpoint ที่ต้องล็อกอิน จึงครอบคลุมทั้งชุดในที่เดียว
โดยไม่ต้องไล่แก้ทีละ endpoint (และ endpoint ที่เพิ่มในอนาคตก็ถูกคุมด้วยอัตโนมัติ)
"""
import json
import logging

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.npd_hrms_api.controllers.main import (
    HrmsApiController, API_ROOT, _err, _ok,
)

_logger = logging.getLogger(__name__)


class HrmsApiControllerSaas(HrmsApiController):

    def _current_employee(self, data=None):
        status = request.env['saas.license'].sudo().get_status()
        if status['locked']:
            # ใช้ AccessError เพื่อให้ _guard แปลงเป็น 401 แล้วแอปเด้งกลับหน้าล็อกอิน
            raise AccessError(status['message'])
        return super()._current_employee(data)

    @http.route(f'{API_ROOT}/login', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def login(self, **kwargs):
        status = request.env['saas.license'].sudo().get_status()
        if status['locked']:
            return _err(status['message'], status=403)
        return super().login(**kwargs)

    @http.route(f'{API_ROOT}/menu', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def menu_data(self, **kwargs):
        """แนบสถานะสัญญาไปกับหน้าแรกของแอป เพื่อขึ้นแบนเนอร์ช่วงผ่อนผัน"""
        response = super().menu_data(**kwargs)
        try:
            if response.status_code == 200:
                payload = json.loads(response.get_data(as_text=True))
                status = request.env['saas.license'].sudo().get_status()
                payload['license'] = {
                    'state': status['state'],
                    'in_grace': status['in_grace'],
                    'days_left': status['days_left'],
                    'message': status['message'],
                }
                response.set_data(json.dumps(payload, ensure_ascii=False))
        except Exception:
            # แบนเนอร์เป็นของเสริม ห้ามทำให้หน้าแรกของแอปพัง
            _logger.exception('แนบสถานะสัญญาเข้าหน้าแรกไม่สำเร็จ')
        return response

    @http.route(f'{API_ROOT}/license', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def license_status(self, **kwargs):
        """ให้แอปดึงไปแสดงสถานะสัญญา — ไม่ต้องล็อกอิน จึงเรียกได้แม้ถูกล็อก"""
        try:
            status = request.env['saas.license'].sudo().get_status()
            return _ok('', {
                'state': status['state'],
                'expire_date': status['expire_date'],
                'days_left': status['days_left'],
                'in_grace': status['in_grace'],
                'locked': status['locked'],
                'message': status['message'],
                'tenant_name': status['tenant_name'],
                'support_phone': status['support_phone'],
            })
        except Exception as exc:
            _logger.exception('อ่านสถานะสัญญาไม่สำเร็จ')
            return _err(str(exc), status=500)
