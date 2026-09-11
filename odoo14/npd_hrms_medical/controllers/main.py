# -*- coding: utf-8 -*-
"""API ค่ารักษาพยาบาล — ต่อยอด controller ของ npd_hrms_api

* POST /manual_time รับไฟล์ได้หลายไฟล์ (ส่งซ้ำชื่อฟิลด์ ``files``) + บัญชีธนาคาร
* GET  /manual_time/medical_info — วงเงินคงเหลือ + รายชื่อธนาคาร ให้แอปใช้กรอกฟอร์ม
* GET  /manual_time/attachment/<คำขอ>/<ไฟล์>/<ชื่อไฟล์> — เปิดไฟล์แนบทีละไฟล์
  (ชื่อไฟล์ท้าย URL ทำให้แอปรู้นามสกุล จึงเปิดรูปในตัวดูรูปได้ — เดิมเปิดไม่ขึ้น)
"""
import base64
import mimetypes
from urllib.parse import quote

from odoo import http
from odoo.http import request

from odoo.addons.npd_hrms_api.controllers.main import (
    API_ROOT, HrmsApiController, _err, _int_or_none, _ok, _payload)

# แอปรุ่นใหม่ส่ง files (หลายไฟล์) — รุ่นเก่าส่ง file / attachment ไฟล์เดียว
UPLOAD_FIELDS = ('files', 'files[]', 'file', 'attachment')


def _uploaded_files():
    """ไฟล์ทั้งหมดใน multipart → [(base64, ชื่อไฟล์)]"""
    found = []
    for key in UPLOAD_FIELDS:
        for uploaded in request.httprequest.files.getlist(key):
            if not uploaded or not uploaded.filename:
                continue
            content = uploaded.read()
            if content:
                found.append((base64.b64encode(content).decode(), uploaded.filename))
    return found


class HrmsMedicalApiController(HrmsApiController):

    def _manual_time_post(self):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            files = _uploaded_files()
            if not files and data.get('attachment_base64'):
                files = [(data['attachment_base64'], data.get('filename') or 'attachment.jpg')]
            result = request.env['hr.manual.time.log'].sudo().api_submit(
                employee_id=employee.id,
                work_date=data.get('work_date'),
                checkin_time=data.get('checkin_time'),
                checkout_time=data.get('checkout_time'),
                reason_type=data.get('reason_type'),
                user_note=data.get('user_note'),
                allowance_type=data.get('allowance_type'),
                amount=data.get('amount'),
                request_id=_int_or_none(data.get('request_id')) or None,
                files=files,
                bank_name=data.get('bank_name'),
                bank_account_number=data.get('bank_account_number'),
                bank_account_name=data.get('bank_account_name'))
            return _ok(result.pop('message', ''), result)
        return run()

    @http.route(f'{API_ROOT}/manual_time/medical_info', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def manual_time_medical_info(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            info = request.env['hr.manual.time.log'].sudo().api_get_medical_info(
                employee.id,
                year=_int_or_none(data.get('year')),
                exclude_id=_int_or_none(data.get('exclude_id')))
            return _ok(info.get('message', ''), info)
        return run()

    @http.route(f'{API_ROOT}/manual_time/attachment/<int:log_id>/<int:attachment_id>/<path:fname>',
                type='http', auth='public', methods=['GET'], csrf=False, cors='*')
    def manual_time_attachment_file(self, log_id, attachment_id, fname=None, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            record = request.env['hr.manual.time.log'].sudo().browse(log_id)
            if not record.exists():
                return _err('ไม่พบไฟล์แนบ', status=404)
            if not self._may_view(employee, record.employee_id):
                return _err('ไม่มีสิทธิ์เข้าถึงไฟล์นี้', status=403)
            if attachment_id:
                attachment = record.attachment_ids.filtered(lambda a: a.id == attachment_id)
                if not attachment:
                    return _err('ไม่พบไฟล์แนบ', status=404)
                content, name, mimetype = attachment.raw, attachment.name, attachment.mimetype
            else:
                if not record.attachment:
                    return _err('ไม่พบไฟล์แนบ', status=404)
                content = base64.b64decode(record.attachment)
                name = record.filename or 'attachment'
                mimetype = mimetypes.guess_type(name)[0]
            return request.make_response(content, headers=[
                ('Content-Type', mimetype or 'application/octet-stream'),
                ('Content-Disposition', "inline; filename*=UTF-8''%s" % quote(name or 'file')),
            ])
        return run()
