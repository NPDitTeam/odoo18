# -*- coding: utf-8 -*-
"""GET /api/hrms/v1/leave/requests/<id>/pdf — ใบลา NPD/HR.03 ให้แอปดู/แชร์/บันทึก"""
from odoo import http
from odoo.http import request, content_disposition

from odoo.addons.npd_hrms_api.controllers.main import (
    API_ROOT, HrmsApiController, _err, _payload)


class HrmsLeaveFormController(HrmsApiController):

    @http.route(f'{API_ROOT}/leave/requests/<int:leave_id>/pdf', type='http',
                auth='public', methods=['GET'], csrf=False, cors='*')
    def leave_form_pdf(self, leave_id, **kwargs):
        @self._guard
        def run():
            employee = self._current_employee(_payload())
            record = request.env['hr.attendance.branch.leave'].sudo().browse(leave_id)
            # ไม่บอกว่ามีใบลาแต่เป็นของคนอื่น — กันไล่เดา id
            if not record.exists() or not self._may_view(employee, record.employee_id):
                return _err('ไม่พบใบลา', status=404)
            report = request.env.ref(
                'npd_hrms_leave_form_jasper.jasper_leave_form_report').sudo()
            # jasper_reports ต้องใช้ lang en_US (ตามตัว controller ของโมดูลเอง)
            pdf, _output = report.with_context(lang='en_US').render_jasper(record.ids, {})
            return request.make_response(pdf, headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', content_disposition('leave_form_%s.pdf' % record.id)),
            ])
        return run()
