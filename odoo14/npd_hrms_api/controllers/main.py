# -*- coding: utf-8 -*-
"""REST API สำหรับแอป HR — แทน PHP บน npdhrms.com ทั้งหมด

ทุก endpoint คืนรูปแบบเดียวกับของเดิม:
    {"status": "success"|"error", "message": "...", "data": ...}

controller ในไฟล์นี้ตั้งใจให้ "บาง" — หน้าที่มีแค่
  1. ตรวจ token / สิทธิ์
  2. แปลงพารามิเตอร์จาก HTTP เป็นค่า Python
  3. เรียกเมธอด ``api_*`` บนโมเดล
  4. ห่อผลลัพธ์เป็น JSON
กฎธุรกิจอยู่ในโมเดลเสมอ เพื่อให้หน้าเว็บ Odoo กับแอปทำงานเหมือนกันเป๊ะ
"""
import base64
import json
import logging

from odoo import http, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

API_ROOT = '/api/hrms/v1'

JSON_CT = 'application/json; charset=utf-8'


def _json(payload, status=200):
    return Response(
        json.dumps(payload, ensure_ascii=False, default=str),
        content_type=JSON_CT, status=status)


def _ok(message='', data=None, **extra):
    payload = {'status': 'success', 'message': message}
    if data is not None:
        payload['data'] = data
    payload.update(extra)
    return _json(payload)


def _err(message, status=400, **extra):
    payload = {'status': 'error', 'message': message}
    payload.update(extra)
    return _json(payload, status=status)


def _payload():
    """อ่านพารามิเตอร์จาก query string + body (JSON หรือ form-data)

    แอปเวอร์ชันต่าง ๆ ส่งมาไม่เหมือนกัน — บางจอเป็น JSON บางจอเป็น multipart
    เพราะต้องแนบไฟล์ จึงรับทั้งสองแบบ

    ต้องแยกตาม Content-Type ไม่ใช่ลองทั้งคู่: การอ่าน ``.form`` ของ multipart
    จะ consume stream ทำให้ ``get_data()`` หลังจากนั้นได้ค่าว่าง
    """
    httprequest = request.httprequest
    data = dict(httprequest.args.to_dict())
    content_type = (httprequest.content_type or '').lower()

    if content_type.startswith('application/json'):
        raw = httprequest.get_data(as_text=True)
        if raw:
            try:
                parsed = json.loads(raw.lstrip('﻿'))
                if isinstance(parsed, dict):
                    data.update(parsed)
            except (ValueError, TypeError):
                _logger.warning('HRMS API: body ไม่ใช่ JSON ที่ถูกต้อง')
    elif content_type:
        data.update(httprequest.form.to_dict())
    return data


def _file_as_base64(field_name='attachment'):
    """อ่านไฟล์แนบจาก multipart → (base64, filename) หรือ (None, None)"""
    uploaded = request.httprequest.files.get(field_name)
    if not uploaded or not uploaded.filename:
        return None, None
    content = uploaded.read()
    if not content:
        return None, None
    return base64.b64encode(content).decode(), uploaded.filename


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class HrmsApiController(http.Controller):

    # ==================================================================
    # Auth helper
    # ==================================================================
    def _current_employee(self, data=None):
        """พนักงานเจ้าของ token ที่แนบมากับ request

        raise AccessError ถ้า token ไม่ถูกต้อง — ตัวห่อ ``_guard`` แปลงเป็น 401
        """
        header = request.httprequest.headers.get('Authorization', '')
        token = header[7:].strip() if header.lower().startswith('bearer ') else ''
        if not token:
            token = (data or {}).get('token') or ''
        device_id = (data or {}).get('device_id') or request.httprequest.headers.get(
            'X-Device-Id')
        employee = request.env['hrms.api.token'].sudo()._resolve(token, device_id)
        if not employee:
            raise AccessError('token ไม่ถูกต้องหรือหมดอายุ กรุณาเข้าสู่ระบบใหม่')
        return employee

    @staticmethod
    def _guard(func):
        """แปลง exception ของ Odoo เป็น JSON error ที่แอปอ่านได้

        สำคัญกับแอปมือถือ: ถ้าปล่อยให้ Odoo คืนหน้า HTML error แอปจะ parse ไม่ผ่าน
        แล้วขึ้นข้อความกำกวมแทนสาเหตุจริง (ปัญหาเดิมของฝั่ง PHP)

        ต้อง rollback เองทุกครั้งที่ดักไว้ — เพราะเมื่อ exception ไม่หลุดออกจาก
        controller Odoo จะถือว่า request สำเร็จแล้ว commit ให้ ทำให้ข้อมูลที่เขียน
        ไปก่อนจุดที่ validate ไม่ผ่าน ค้างอยู่ในฐานข้อมูล (เช่น คำขอเบิกเบี้ยเลี้ยง
        ที่ไม่ได้กรอกจำนวนเงิน ถูกบันทึกทั้งที่ API ตอบ error)
        """
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except AccessError as exc:
                request.env.cr.rollback()
                return _err(str(exc), status=401)
            except (UserError, ValidationError) as exc:
                request.env.cr.rollback()
                return _err(str(exc), status=400)
            except Exception as exc:
                _logger.exception('HRMS API error')
                request.env.cr.rollback()
                return _err('เกิดข้อผิดพลาดบนเซิร์ฟเวอร์: %s' % exc, status=500)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    # ==================================================================
    # เวอร์ชันแอป — ไม่ต้องล็อกอิน (แอปเรียกก่อนหน้า login)
    # ==================================================================
    @http.route(f'{API_ROOT}/version', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def app_version(self, **kwargs):
        try:
            return _json(request.env['hrms.app.release'].sudo().api_get_latest())
        except Exception as exc:
            _logger.exception('HRMS API version error')
            return _err(str(exc), status=500)

    # ==================================================================
    # รหัสองค์กร — แอปเรียกก่อน login เพื่อรู้ว่าต้องต่อไปเซิร์ฟเวอร์ไหน
    # และแสดงชื่อ/โลโก้/สีขององค์กรนั้น (รองรับการปล่อยเช่า)
    # ==================================================================
    @http.route(f'{API_ROOT}/tenant/resolve', type='http', auth='public',
                methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def tenant_resolve(self, **kwargs):
        try:
            code = str(_payload().get('code') or '').strip()
            if not code:
                return _err('กรุณากรอกรหัสองค์กร', status=400)
            tenant = request.env['hrms.tenant'].sudo().api_resolve(code)
            if not tenant:
                # ไม่บอกว่ารหัสมีอยู่แต่ปิดใช้งาน เพื่อไม่ให้ไล่เดารหัสลูกค้ารายอื่นได้
                return _err('ไม่พบรหัสองค์กรนี้ กรุณาตรวจสอบกับฝ่ายบุคคล',
                            status=404)
            return _ok('', tenant)
        except Exception as exc:
            _logger.exception('HRMS API tenant resolve error')
            return _err('เกิดข้อผิดพลาดบนเซิร์ฟเวอร์: %s' % exc, status=500)

    @http.route(f'{API_ROOT}/tenant/logo', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def tenant_logo(self, **kwargs):
        code = str(_payload().get('code') or '').strip().lower()
        tenant = request.env['hrms.tenant'].sudo().search(
            [('code', '=', code)], limit=1)
        if not tenant or not tenant.logo:
            return Response(status=404)
        return Response(base64.b64decode(tenant.logo), content_type='image/png')

    # ==================================================================
    # เข้าสู่ระบบ
    # ==================================================================
    @http.route(f'{API_ROOT}/login', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def login(self, **kwargs):
        try:
            data = _payload()
            pin = str(data.get('pin') or '').strip()
            device_id = str(data.get('device_id') or '').strip()
            ip_address = request.httprequest.remote_addr

            if not pin.isdigit() or len(pin) != 6:
                return _err('รหัส PIN ต้องเป็นตัวเลข 6 หลักเท่านั้น', status=400)
            if not device_id:
                return _err('กรุณาส่ง device_id มาด้วย', status=400)

            # กันการไล่เดา PIN — PIN 6 หลักมีแค่ 1 ล้านแบบ
            Attempt = request.env['hrms.api.login.attempt'].sudo()
            wait_seconds = Attempt._check_blocked(device_id, ip_address)
            if wait_seconds:
                return _err(
                    'ใส่ PIN ผิดหลายครั้งเกินไป กรุณารออีก %d นาทีแล้วลองใหม่'
                    % max(1, wait_seconds // 60), status=429)

            Employee = request.env['employee.salary'].sudo()
            employee = Employee.search(
                [('pin', '=', pin), ('status', '=', 'active')], limit=1)
            if not employee:
                Attempt._register_failure(device_id, ip_address)
                return _err('รหัส PIN ไม่ถูกต้อง หรือบัญชีไม่ใช้งาน', status=401)

            # บัญชีถูกล็อกจากการเดา PIN
            now = fields.Datetime.now()
            if employee.login_locked_until and employee.login_locked_until > now:
                return _err(
                    'บัญชีถูกล็อกชั่วคราวจากการใส่ PIN ผิดหลายครั้ง '
                    'กรุณาติดต่อฝ่ายบุคคล', status=403)

            # ผูกอุปกรณ์ — กฎเดียวกับ api_login_pin_test1.php เดิม
            registered = (employee.device_id or '').strip()
            if employee.allow_multi_login:
                if not registered:
                    employee.write({'device_id': device_id, 'device_bound_at': now})
            elif not registered:
                employee.write({'device_id': device_id, 'device_bound_at': now})
            elif registered != device_id:
                return _err('บัญชีนี้ล็อกอินจากอุปกรณ์อื่นแล้ว', status=403)

            token = request.env['hrms.api.token'].sudo()._issue(
                employee,
                device_id=device_id,
                user_agent=request.httprequest.headers.get('User-Agent'),
                ip_address=ip_address)

            Attempt._register_success(device_id, ip_address)
            employee.write({'failed_login_count': 0, 'login_locked_until': False})

            is_approver = bool(request.env['approver.relations'].sudo().search_count(
                [('approver_user_id', '=', employee.id)]))

            return _json({
                'status': 'success',
                'message': 'ล็อกอินสำเร็จ',
                'token': token.token,
                'expires_at': token.expires_at.isoformat(),
                'user': {
                    'id': employee.id,
                    'employee_code': employee.employee_code or '',
                    'username': employee.full_name or '',
                    'firstname': employee.firstname or '',
                    'lastname': employee.lastname or '',
                    'department': employee.department_id.name or '',
                    'position': employee.position_id.name or '',
                    'branch': employee.branch_id.name or '',
                    'company': employee.company_id.name or '',
                    'status': employee.status or '',
                    'device_id': employee.device_id or device_id,
                },
                'is_approver': is_approver,
                'mode': 'production',
            })
        except Exception as exc:
            _logger.exception('HRMS API login error')
            return _err('เกิดข้อผิดพลาดบนเซิร์ฟเวอร์: %s' % exc, status=500)

    @http.route(f'{API_ROOT}/logout', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def logout(self, **kwargs):
        header = request.httprequest.headers.get('Authorization', '')
        token = header[7:].strip() if header.lower().startswith('bearer ') else ''
        if token:
            record = request.env['hrms.api.token'].sudo().search(
                [('token', '=', token)], limit=1)
            if record:
                record.action_revoke()
        return _ok('ออกจากระบบเรียบร้อย')

    # ==================================================================
    # หน้าแรก / เมนู
    # ==================================================================
    @http.route(f'{API_ROOT}/menu', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def menu_data(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            Relations = request.env['approver.relations'].sudo()
            subordinate_ids = Relations.search(
                [('approver_user_id', '=', employee.id)]).mapped('user_id').ids
            subordinate_ids = [eid for eid in subordinate_ids if eid != employee.id]

            pending_leave = pending_addtime = 0
            if subordinate_ids:
                pending_leave = request.env['hr.attendance.branch.leave'].sudo(
                ).search_count([
                    ('employee_id', 'in', subordinate_ids),
                    ('state', '=', 'รออนุมัติ')])
                pending_addtime = request.env['hr.manual.time.log'].sudo(
                ).search_count([
                    ('employee_id', 'in', subordinate_ids),
                    ('state', '=', 'รออนุมัติ')])

            history = request.env['hr.attendance.branch'].sudo(
            ).api_get_recent_history(employee.id, days=3)

            return _json({
                'status': 'success',
                'is_approver': bool(subordinate_ids),
                'pending_addtime_count': pending_addtime,
                'pending_leave_count': pending_leave,
                'checkin_history': history,
                'warning_count': request.env['employee.warning'].sudo(
                ).api_get_warning_count(employee.employee_code),
            })
        return run()

    @http.route(f'{API_ROOT}/employee/profile', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def employee_profile(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            return _ok('', employee._api_profile())
        return run()

    # ==================================================================
    # ลงเวลา
    # ==================================================================
    @http.route(f'{API_ROOT}/checkin/status', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def checkin_status(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            data = request.env['hr.attendance.branch'].sudo().api_checkin_status(
                employee.id)
            return _ok('', data)
        return run()

    @http.route(f'{API_ROOT}/checkin', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def checkin_save(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            result = request.env['hr.attendance.branch'].sudo().api_save_checkin(
                employee_id=employee.id,
                check_type=data.get('type') or data.get('check_type'),
                latitude=data.get('lat') or data.get('latitude'),
                longitude=data.get('lng') or data.get('longitude'),
                accuracy=data.get('accuracy'),
                address=data.get('address'))
            return _ok(result.pop('message', ''), result)
        return run()

    @http.route(f'{API_ROOT}/checkin/history', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def checkin_history(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            result = request.env['hr.attendance.branch'].sudo().api_get_history(
                employee.id, month=data.get('month'), year=data.get('year'))
            return _json({'status': 'success', **result})
        return run()

    # ==================================================================
    # สิทธิ์การลา
    # ==================================================================
    @http.route(f'{API_ROOT}/leave/allowance', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def leave_allowance(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            result = request.env['hrms.leave.balance'].sudo().api_get_allowance(
                employee.employee_code, year=data.get('year'))
            if not result:
                return _err('ไม่พบข้อมูลสิทธิ์การลาของพนักงาน', status=404)
            return _ok('', result)
        return run()

    @http.route(f'{API_ROOT}/leave/allowance/check', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def leave_allowance_check(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            leave_type = data.get('leave_type')
            if not leave_type:
                return _err('ไม่พบ leave_type', status=400)
            result = request.env['hrms.leave.balance'].sudo().api_check_allowance(
                employee.employee_code, leave_type, year=data.get('year'))
            if not result:
                return _err('ไม่พบข้อมูลสิทธิ์การลาของพนักงาน', status=404)
            return _ok('', result)
        return run()

    @http.route(f'{API_ROOT}/leave/types', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def leave_types(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            types = request.env['hrms.leave.type'].sudo().search(
                [('company_id', '=', (employee.company_id or request.env.company).id)])
            return _ok('', [{
                'id': leave_type.id,
                'code': leave_type.code or '',
                'name': leave_type.name or '',
                'is_paid': leave_type.is_paid,
                'requires_attachment': leave_type.requires_attachment,
            } for leave_type in types])
        return run()

    # ==================================================================
    # ใบลา
    # ==================================================================
    @http.route(f'{API_ROOT}/leave/requests', type='http', auth='public',
                methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def leave_requests(self, **kwargs):
        """GET = ประวัติการลา, POST = ยื่น/แก้ไขใบลา

        รวมสองเมธอดไว้ที่ route เดียวเหมือนฝั่ง PHP (leave_requests.php)
        และเลี่ยงการประกาศ path ซ้ำสอง route ซึ่งทำให้ routing กำกวม
        """
        if request.httprequest.method == 'GET':
            return self._leave_requests_get()
        return self._leave_requests_post()

    def _leave_requests_get(self):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            records = request.env['hr.attendance.branch.leave'].sudo().api_get_history(
                employee.id,
                limit=_int_or_none(data.get('limit')) or 7,
                month=data.get('month'), year=data.get('year'))
            return _ok('Leave history fetched successfully.', records)
        return run()

    def _leave_requests_post(self):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            attachment, filename = _file_as_base64('attachment')
            if not attachment and data.get('attachment_base64'):
                attachment = data['attachment_base64']
                filename = data.get('filename') or 'attachment'
            result = request.env['hr.attendance.branch.leave'].sudo().api_submit(
                employee_id=employee.id,
                leave_type=data.get('leave_type'),
                leave_start_date=data.get('leave_start_date'),
                start_time=data.get('leave_statr_time') or data.get('leave_start_time'),
                leave_end_date=data.get('leave_end_date'),
                end_time=data.get('leave_end_time'),
                note=data.get('note'),
                request_id=_int_or_none(data.get('request_id')) or None,
                attachment=attachment,
                filename=filename,
                clear_attachment=data.get('existing_file_path') == '')
            return _ok(result.pop('message', ''), result)
        return run()

    @http.route(f'{API_ROOT}/leave/requests/cancel', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def leave_request_cancel(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            result = request.env['hr.attendance.branch.leave'].sudo().api_cancel(
                request_id=data.get('request_id'), employee_id=employee.id)
            return _ok(result.pop('message', ''), result)
        return run()

    @http.route(f'{API_ROOT}/leave/approvals', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def leave_approvals(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            data = request.env['hr.attendance.branch.leave'].sudo(
            ).api_get_approval_queue(employee.id)
            return _ok('Requests fetched successfully.', data)
        return run()

    @http.route(f'{API_ROOT}/leave/approvals/action', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def leave_approval_action(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            result = request.env['hr.attendance.branch.leave'].sudo(
            ).api_approve_action(
                approver_id=employee.id,
                request_id=data.get('request_id'),
                action=data.get('action'),
                reason=data.get('reason'),
                new_state=data.get('new_state'))
            return _ok(result.pop('message', ''), result)
        return run()

    @http.route(f'{API_ROOT}/leave/attachment/<int:leave_id>', type='http',
                auth='public', methods=['GET'], csrf=False, cors='*')
    def leave_attachment(self, leave_id, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            record = request.env['hr.attendance.branch.leave'].sudo().browse(leave_id)
            if not record.exists() or not record.attachment:
                return _err('ไม่พบไฟล์แนบ', status=404)
            if not self._may_view(employee, record.employee_id):
                return _err('ไม่มีสิทธิ์เข้าถึงไฟล์นี้', status=403)
            return request.make_response(
                base64.b64decode(record.attachment), headers=[
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition',
                     'inline; filename="%s"' % (record.filename or 'attachment')),
                ])
        return run()

    # ==================================================================
    # เพิ่มเวลา
    # ==================================================================
    @http.route(f'{API_ROOT}/manual_time', type='http', auth='public',
                methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def manual_time(self, **kwargs):
        """GET = ประวัติการเพิ่มเวลา, POST = ยื่น/แก้ไขคำขอ"""
        if request.httprequest.method == 'GET':
            return self._manual_time_get()
        return self._manual_time_post()

    def _manual_time_get(self):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            records = request.env['hr.manual.time.log'].sudo().api_get_history(
                employee.id,
                limit=_int_or_none(data.get('limit')) or 7,
                month=data.get('month'), year=data.get('year'))
            return _ok('', records)
        return run()

    def _manual_time_post(self):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            attachment, filename = _file_as_base64('file')
            if not attachment:
                attachment, filename = _file_as_base64('attachment')
            if not attachment and data.get('attachment_base64'):
                attachment = data['attachment_base64']
                filename = data.get('filename') or 'attachment'
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
                attachment=attachment,
                filename=filename)
            return _ok(result.pop('message', ''), result)
        return run()

    @http.route(f'{API_ROOT}/manual_time/cancel', type='http', auth='public',
                methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def manual_time_cancel(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            result = request.env['hr.manual.time.log'].sudo().api_cancel(
                request_id=data.get('request_id'), employee_id=employee.id)
            return _ok(result.pop('message', ''), result)
        return run()

    @http.route(f'{API_ROOT}/manual_time/approvals', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def manual_time_approvals(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            data = request.env['hr.manual.time.log'].sudo().api_get_approval_queue(
                employee.id)
            return _ok('Requests fetched successfully.', data)
        return run()

    @http.route(f'{API_ROOT}/manual_time/approvals/action', type='http',
                auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def manual_time_approval_action(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            result = request.env['hr.manual.time.log'].sudo().api_approve_action(
                approver_id=employee.id,
                request_id=data.get('request_id'),
                action=data.get('action'),
                reason=data.get('reason'),
                new_state=data.get('new_state'))
            return _ok(result.pop('message', ''), result)
        return run()

    @http.route(f'{API_ROOT}/manual_time/attachment/<int:log_id>', type='http',
                auth='public', methods=['GET'], csrf=False, cors='*')
    def manual_time_attachment(self, log_id, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            record = request.env['hr.manual.time.log'].sudo().browse(log_id)
            if not record.exists() or not record.attachment:
                return _err('ไม่พบไฟล์แนบ', status=404)
            if not self._may_view(employee, record.employee_id):
                return _err('ไม่มีสิทธิ์เข้าถึงไฟล์นี้', status=403)
            return request.make_response(
                base64.b64decode(record.attachment), headers=[
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition',
                     'inline; filename="%s"' % (record.filename or 'attachment')),
                ])
        return run()

    # ==================================================================
    # ข้อมูลประกอบ
    # ==================================================================
    @http.route(f'{API_ROOT}/allowance_types', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def allowance_types(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            data = request.env['allowance.management'].sudo(
            ).api_get_allowances_by_employee_code(employee.employee_code)
            return _ok('', data)
        return run()

    @http.route(f'{API_ROOT}/work_schedule', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def work_schedule(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            data = request.env['hr.work.schedule'].sudo().api_get_schedule(
                employee.employee_code)
            if not data:
                return _err('ไม่พบตารางงาน', status=404)
            return _ok('', data)
        return run()

    @http.route(f'{API_ROOT}/holidays', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def holidays(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            result = request.env['payroll.holiday'].sudo().api_get_holidays(
                year=data.get('year'),
                company_id=(employee.company_id or request.env.company).id)
            return _ok('', result)
        return run()

    @http.route(f'{API_ROOT}/late_minutes', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def late_minutes(self, **kwargs):
        """นาทีที่สายรายวันของเดือนนั้น — แอปเอาไปแสดงใต้เวลาเข้างานและแจ้งเตือน

        ตัวเลขมาจากเอนจินเดียวกับที่คิดเงินเดือน ไม่ได้คำนวณซ้ำในแอป
        ถ้ายังไม่ติดตั้งโมดูลเงินเดือน ให้คืนว่างแทนที่จะพัง เพราะหน้าประวัติ
        การลงเวลาต้องเปิดได้อยู่ดี
        """
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            if 'payroll.lateness.rule' not in request.env:
                return _ok('', {})
            today = fields.Date.context_today(employee)
            result = request.env['payroll.lateness.rule'].sudo(
            ).api_get_late_minutes(
                employee.employee_code,
                data.get('month') or today.month,
                data.get('year') or today.year)
            return _ok('', result)
        return run()

    @http.route(f'{API_ROOT}/saturday_quota', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def saturday_quota(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            quota = request.env['saturday.leave.config'].sudo(
            ).api_get_saturday_quota(employee.employee_code)
            return _ok('', {'days_allowed': quota})
        return run()

    @http.route(f'{API_ROOT}/warnings', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def warnings(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            Warning_ = request.env['employee.warning'].sudo()
            return _ok('', {
                'warning_count': Warning_.api_get_warning_count(
                    employee.employee_code),
                'warnings': Warning_.api_get_warnings_by_employee_code(
                    employee.employee_code),
            })
        return run()

    @http.route(f'{API_ROOT}/warnings/attachment/<int:line_id>', type='http',
                auth='public', methods=['GET'], csrf=False, cors='*')
    def warning_attachment(self, line_id, **kwargs):
        """ไฟล์แนบของใบเตือน

        พนักงานเปิดได้เฉพาะใบเตือนของตัวเอง — ใบเตือนเป็นเอกสารทางวินัย
        ถ้าปล่อยให้เดา id แล้วเปิดได้ จะกลายเป็นช่องอ่านประวัติวินัยของคนอื่น
        """
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            line = request.env['employee.warning.line'].sudo().browse(line_id)
            if not line.exists() or not line.attachment:
                return _err('ไม่พบไฟล์แนบ', status=404)
            owner = line.warning_id.employee_id
            if not self._may_view(employee, owner):
                return _err('ไม่มีสิทธิ์เข้าถึงไฟล์นี้', status=403)
            return request.make_response(
                base64.b64decode(line.attachment), headers=[
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition',
                     'inline; filename="%s"'
                     % (line.attachment_filename or 'warning')),
                ])
        return run()

    @http.route(f'{API_ROOT}/approvers', type='http', auth='public',
                methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def approvers(self, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            return _ok('', request.env['approver.relations'].sudo().api_get_approvers(
                employee.employee_code))
        return run()

    # ==================================================================
    # สลิปเงินเดือน — ต้องติดตั้งโมดูล npd_hrms_payroll ก่อน
    # ==================================================================
    @http.route(f'{API_ROOT}/payslip', type='http', auth='public',
                methods=['GET', 'POST', 'OPTIONS'], csrf=False, cors='*')
    def payslip(self, **kwargs):
        @self._guard
        def run():
            data = _payload()
            employee = self._current_employee(data)
            if 'payroll.salary' not in request.env:
                return _err(
                    'ยังไม่ได้ติดตั้งโมดูลเงินเดือน (npd_hrms_payroll)', status=501)
            records = request.env['payroll.salary'].sudo().api_get_payslips(
                employee.employee_code,
                month=data.get('month'), year=data.get('year'))
            if not records:
                return _json({
                    'status': 'error',
                    'message': 'ไม่พบข้อมูลสลิปเงินเดือน',
                    'data': [],
                })
            return _ok('Data fetched successfully.', records)
        return run()

    # ==================================================================
    # Helper
    # ==================================================================
    @staticmethod
    def _may_view(viewer, owner):
        """ดูข้อมูลของตัวเองได้เสมอ — ของคนอื่นได้เฉพาะเมื่อเป็นผู้อนุมัติของเขา"""
        if viewer.id == owner.id:
            return True
        return bool(request.env['approver.relations'].sudo().search_count([
            ('approver_user_id', '=', viewer.id),
            ('user_id', '=', owner.id),
        ]))
