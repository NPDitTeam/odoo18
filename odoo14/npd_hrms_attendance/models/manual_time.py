# -*- coding: utf-8 -*-
"""ขอเพิ่มเวลา / เบิกเบี้ยเลี้ยง

แทนตาราง MySQL ``manual_time_logs`` และไฟล์ manual_time_logs_test.php /
approve_add_time_screen_test.php / cancel_manual_time_log.php

"ประเภทการเพิ่มเวลา" เปลี่ยนจาก Selection ค่าคงที่ 10 ค่า เป็นข้อมูลหลัก
(``hrms.manual.time.reason``) ด้วยเหตุผล 2 ข้อ:

1. รองรับการปล่อยเช่าระบบ — บริษัทที่เช่าไปตั้งประเภทของตัวเองได้
2. แก้บั๊กเงียบของเดิม: ฝั่ง PHP ตรวจว่าต้องกรอกจำนวนเงินโดยเทียบสตริง
   'ค่าเบี๊ยเลี้ยงออกนอกสถานที่' ซึ่งสะกดไม่ตรงกับค่าจริงที่ Odoo ใช้
   ('ค่าเบี้ยเลี้ยงออกนอกสถานที่') → การตรวจนั้นไม่เคยทำงาน
   ตอนนี้ใช้ธง ``requires_amount`` บนเรคคอร์ดแทนการเทียบข้อความ
"""
import base64
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

MANUAL_TIME_STATES = [
    ('รออนุมัติ', 'รออนุมัติ'),
    ('อนุมัติ', 'อนุมัติ'),
    ('ไม่อนุมัติ', 'ไม่อนุมัติ'),
    ('ยกเลิก', 'ยกเลิก'),
]

ALLOWED_ATTACHMENT_EXT = ('jpg', 'jpeg', 'png', 'pdf')
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024


class HrmsManualTimeReason(models.Model):
    _name = 'hrms.manual.time.reason'
    _description = 'ประเภทการเพิ่มเวลา'
    _order = 'sequence, id'

    # ไม่ใส่ translate=True ด้วยเหตุผลเดียวกับ hrms.leave.type.name
    name = fields.Char(string='ชื่อประเภท', required=True)
    code = fields.Char(
        string='รหัสอ้างอิง',
        help='รหัสสั้นสำหรับอ้างในโค้ด/รายงาน เช่น offsite_allowance')
    sequence = fields.Integer(string='ลำดับ', default=10)
    active = fields.Boolean(string='ใช้งาน', default=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)

    requires_amount = fields.Boolean(
        string='ต้องกรอกจำนวนเงิน',
        help='แอปจะบังคับให้กรอกจำนวนเงินก่อนส่งคำขอประเภทนี้')
    requires_attachment = fields.Boolean(
        string='ต้องแนบเอกสาร',
        help='เช่น ค่ารักษาพยาบาลที่ต้องแนบใบเสร็จ')
    requires_allowance_type = fields.Boolean(
        string='ต้องเลือกรายการเบี้ยเลี้ยง',
        help='ให้ผู้ใช้เลือกจากรายการที่ประกาศไว้ในเมนูจัดการค่าเบี้ยเลี้ยง')
    is_overtime = fields.Boolean(
        string='เป็นการขอ OT',
        help='ระบบจะนำชั่วโมงไปคิดค่าล่วงเวลาแทนการคิดเป็นจำนวนเงินตรง ๆ')
    ot_kind = fields.Selection([
        ('request', 'ขอ OT ปกติ (ระบบแยกวันธรรมดา/วันหยุดประจำสัปดาห์ให้เอง)'),
        ('holiday', 'ทำงานวันหยุด (อัตราวันหยุดเสมอ)'),
    ], string='ชนิด OT',
        help='ใช้ตอนคิดค่าล่วงเวลา — "ขอ OT ปกติ" ระบบดูว่าอยู่นอกกะไหมแล้วเลือกอัตราให้ '
             'ส่วน "ทำงานวันหยุด" ได้อัตราวันหยุดเสมอไม่ว่าวันไหน')
    counts_as_attendance = fields.Boolean(
        string='ถือว่ามาทำงานจริง',
        help='ใช้แทนการลงเวลาเข้า-ออกตอนคิดสาย/ขาดงาน เช่น ลืมลงเวลา ทำงานนอกสถานที่ ระบบมีปัญหา — '
             'ไม่ควรติ๊กกับรายการที่เป็น "เงิน" เช่น ขอโอที หรือเบิกเบี้ยเลี้ยง')

    payroll_income_field = fields.Char(
        string='ฟิลด์รายได้ในสลิป',
        help='ชื่อฟิลด์บน payroll.salary ที่จะรับยอดรวมของประเภทนี้ '
             'เช่น income_allowance, income_food — เว้นว่างถ้าไม่เข้าสลิป')
    payroll_line_label = fields.Char(
        string='ชื่อรายการในสลิป',
        help='ข้อความที่จะแสดงเป็นชื่อรายการในสลิปเงินเดือน')

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'ชื่อประเภทนี้มีอยู่แล้วในบริษัทนี้'),
    ]


class HrManualTimeLog(models.Model):
    _name = 'hr.manual.time.log'
    _description = 'เพิ่มเวลา'
    _inherit = ['mail.thread']
    _order = 'work_date desc, id desc'
    _rec_name = 'display_summary'

    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True,
        ondelete='cascade', index=True)
    employee_code = fields.Char(
        string='รหัสพนักงาน', related='employee_id.employee_code',
        store=True, readonly=True, index=True)
    username = fields.Char(
        string='ชื่อผู้ใช้งาน', related='employee_id.full_name',
        store=True, readonly=True)
    branch_id = fields.Many2one(
        'res.branch', string='สาขา', related='employee_id.branch_id',
        store=True, readonly=True)
    department_id = fields.Many2one(
        'hr.department.custom', string='แผนก',
        related='employee_id.department_id', store=True, readonly=True)
    position_id = fields.Many2one(
        'hr.position.custom', string='ตำแหน่ง',
        related='employee_id.position_id', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', related='employee_id.company_id',
        store=True, readonly=True)

    work_date = fields.Date(string='วันที่ทำงาน', required=True, index=True, tracking=True)
    checkin_time = fields.Char(string='เวลาเข้างาน', required=True)
    checkout_time = fields.Char(string='เวลาออกงาน', required=True)

    reason_type_id = fields.Many2one(
        'hrms.manual.time.reason', string='ประเภทการเพิ่มเวลา',
        required=True, ondelete='restrict', tracking=True)
    reason_type_name = fields.Char(
        string='ประเภท (ชื่อ)', related='reason_type_id.name',
        store=True, readonly=True)
    allowance_type = fields.Char(string='รายการประเภทค่าเบี้ยเลี้ยง')
    amount = fields.Float(string='จำนวนเงิน (บาท)', tracking=True)

    user_note = fields.Char(string='หมายเหตุผู้ใช้')
    reason = fields.Char(string='หมายเหตุผู้อนุมัติ')
    state = fields.Selection(
        MANUAL_TIME_STATES, string='สถานะ', default='รออนุมัติ',
        required=True, tracking=True, index=True)
    approved_by = fields.Many2one(
        'employee.salary', string='ผู้อนุมัติ', readonly=True)
    approved_at = fields.Datetime(string='วันที่อนุมัติ', readonly=True)

    attachment = fields.Binary(string='ไฟล์แนบ', attachment=True)
    filename = fields.Char(string='ชื่อไฟล์')

    display_summary = fields.Char(
        string='รายการ', compute='_compute_display_summary', store=True)

    @api.depends('username', 'reason_type_name', 'work_date')
    def _compute_display_summary(self):
        for rec in self:
            parts = [rec.username or '', rec.reason_type_name or '']
            if rec.work_date:
                parts.append(rec.work_date.strftime('%d/%m/%Y'))
            rec.display_summary = ' - '.join(part for part in parts if part)

    # ------------------------------------------------------------------
    # Constraints — กฎเดียวกันทั้งหน้าเว็บและแอป
    # ------------------------------------------------------------------
    @api.constrains('reason_type_id', 'amount', 'attachment', 'allowance_type')
    def _check_reason_requirements(self):
        for rec in self:
            if rec.state not in ('รออนุมัติ', 'อนุมัติ'):
                continue
            reason = rec.reason_type_id
            if reason.requires_amount and (not rec.amount or rec.amount <= 0):
                raise ValidationError(
                    'ประเภท "%s" ต้องกรอกจำนวนเงิน' % reason.name)
            if reason.requires_attachment and not rec.attachment:
                raise ValidationError(
                    'ประเภท "%s" ต้องแนบเอกสารประกอบ' % reason.name)
            if reason.requires_allowance_type and not rec.allowance_type:
                raise ValidationError(
                    'ประเภท "%s" ต้องเลือกรายการค่าเบี้ยเลี้ยง' % reason.name)

    @api.constrains('filename', 'attachment')
    def _check_attachment(self):
        for rec in self:
            if not rec.attachment:
                continue
            if rec.filename:
                ext = rec.filename.rsplit('.', 1)[-1].lower() if '.' in rec.filename else ''
                if ext not in ALLOWED_ATTACHMENT_EXT:
                    raise ValidationError(
                        'รองรับเฉพาะไฟล์ %s เท่านั้น'
                        % ', '.join(e.upper() for e in ALLOWED_ATTACHMENT_EXT))
            try:
                size = len(base64.b64decode(rec.attachment))
            except Exception:
                continue
            if size > MAX_ATTACHMENT_BYTES:
                raise ValidationError('ไฟล์ต้องมีขนาดไม่เกิน 5MB')

    # ------------------------------------------------------------------
    # ปุ่มดำเนินการ
    # ------------------------------------------------------------------
    def _current_employee(self):
        return self.env['employee.salary'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)

    def action_approve(self, approver=None):
        for rec in self:
            if rec.state != 'รออนุมัติ':
                raise UserError('อนุมัติได้เฉพาะรายการที่สถานะ "รออนุมัติ"')
            rec.write({
                'state': 'อนุมัติ',
                'reason': False,
                'approved_by': (approver or rec._current_employee()).id or False,
                'approved_at': fields.Datetime.now(),
            })
        return True

    def action_disapprove(self, reason=None, approver=None):
        for rec in self:
            if rec.state != 'รออนุมัติ':
                raise UserError('ไม่อนุมัติได้เฉพาะรายการที่สถานะ "รออนุมัติ"')
            rec.write({
                'state': 'ไม่อนุมัติ',
                'reason': reason or 'ไม่มีเหตุผล',
                'approved_by': (approver or rec._current_employee()).id or False,
                'approved_at': fields.Datetime.now(),
            })
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == 'ยกเลิก':
                continue
            rec.write({'state': 'ยกเลิก'})
        return True

    def action_reset_to_pending(self):
        self.write({
            'state': 'รออนุมัติ',
            'reason': False,
            'approved_by': False,
            'approved_at': False,
        })
        return True

    # ------------------------------------------------------------------
    # API สำหรับแอป
    # ------------------------------------------------------------------
    def _as_dict(self, base_url=''):
        """รูปแบบเดียวกับที่ manual_time_logs_test.php ส่งให้แอป"""
        self.ensure_one()
        approver = self.approved_by
        return {
            'id': self.id,
            'user_id': self.employee_id.id,
            'employee_code': self.employee_code or '',
            'username': self.username or '',
            'firstname': self.employee_id.firstname or '',
            'lastname': self.employee_id.lastname or '',
            'work_date': self.work_date.isoformat() if self.work_date else '',
            'checkin_time': self.checkin_time or '',
            'checkout_time': self.checkout_time or '',
            'department': self.department_id.name or '',
            'position': self.position_id.name or '',
            'branch': self.branch_id.name or '',
            'company': self.company_id.name or '',
            'state': self.state or '',
            'reason': self.reason or '',
            'user_note': self.user_note or '',
            'reason_type': self.reason_type_name or '',
            'allowance_type': self.allowance_type or '',
            'amount': self.amount or 0.0,
            'file_path': (
                '%s/api/hrms/v1/manual_time/attachment/%s' % (base_url.rstrip('/'), self.id)
                if self.attachment else ''),
            'approved_by': approver.id if approver else None,
            'approver_firstname': approver.firstname if approver else '',
            'approver_lastname': approver.lastname if approver else '',
            'approved_at': self.approved_at.strftime('%Y-%m-%d %H:%M:%S') if self.approved_at else '',
            'created_at': self.create_date.strftime('%Y-%m-%d %H:%M:%S') if self.create_date else '',
        }

    @api.model
    def _resolve_reason_type(self, employee, reason_type):
        Reason = self.env['hrms.manual.time.reason'].sudo()
        company = employee.company_id or self.env.company
        domain = [('company_id', '=', company.id)]
        if isinstance(reason_type, int):
            record = Reason.browse(reason_type)
            if record.exists():
                return record
        else:
            text = str(reason_type or '').strip()
            record = Reason.search(domain + [('name', '=', text)], limit=1)
            if not record:
                record = Reason.search(domain + [('code', '=', text)], limit=1)
            if record:
                return record
        raise UserError('ไม่พบประเภทการเพิ่มเวลา "%s"' % reason_type)

    @api.model
    def api_submit(self, employee_id, work_date, checkin_time, checkout_time,
                   reason_type, user_note=None, allowance_type=None, amount=None,
                   request_id=None, attachment=None, filename=None):
        """ยื่น/แก้ไขคำขอเพิ่มเวลา — แทน POST ของ manual_time_logs_test.php"""
        employee = self.env['employee.salary'].sudo().browse(int(employee_id))
        if not employee.exists():
            raise UserError('ไม่พบข้อมูลพนักงาน')
        if not (work_date and checkin_time and checkout_time):
            raise UserError('ข้อมูลไม่ครบถ้วน (วันที่ทำงาน เวลาเข้า เวลาออก)')

        reason = self._resolve_reason_type(employee, reason_type)
        allowance_type = (allowance_type or '').strip() or False
        amount_value = float(amount) if amount not in (None, '', False) else 0.0

        vals = {
            'employee_id': employee.id,
            'work_date': work_date,
            'checkin_time': checkin_time,
            'checkout_time': checkout_time,
            'reason_type_id': reason.id,
            'user_note': user_note or False,
            'allowance_type': allowance_type,
            'amount': amount_value,
        }
        if attachment:
            vals.update({'attachment': attachment, 'filename': filename or 'attachment'})

        if request_id:
            record = self.sudo().browse(int(request_id))
            if not record.exists() or record.employee_id != employee:
                raise UserError('ไม่พบคำขอที่ต้องการแก้ไข')
            if record.state != 'รออนุมัติ':
                raise UserError('ไม่สามารถแก้ไขได้เนื่องจากสถานะไม่ใช่ "รออนุมัติ"')
            record.write(vals)
            return {'id': record.id, 'message': 'แก้ไขเวลาเรียบร้อยแล้ว'}

        record = self.sudo().create(vals)
        return {'id': record.id,
                'message': 'บันทึกเวลาเรียบร้อยแล้ว, กรุณารอการอนุมัติ'}

    @api.model
    def api_get_history(self, employee_id, limit=7, month=None, year=None):
        domain = [('employee_id', '=', int(employee_id))]
        if month and year:
            import calendar
            month, year = int(month), int(year)
            last_day = calendar.monthrange(year, month)[1]
            domain += [
                ('work_date', '>=', fields.Date.to_date('%04d-%02d-01' % (year, month))),
                ('work_date', '<=', fields.Date.to_date(
                    '%04d-%02d-%02d' % (year, month, last_day))),
            ]
            limit = None
        records = self.sudo().search(
            domain, order='create_date desc', limit=limit or None)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        return [rec._as_dict(base_url) for rec in records]

    @api.model
    def api_get_approval_queue(self, approver_id):
        """รายการรออนุมัติ + ประวัติ 7 วัน — แทน approve_add_time_screen_test.php"""
        from datetime import timedelta
        approver = self.env['employee.salary'].sudo().browse(int(approver_id))
        if not approver.exists():
            raise UserError('ไม่พบข้อมูลผู้ใช้')

        employee_ids = self.env['approver.relations'].sudo().search(
            [('approver_user_id', '=', approver.id)]).mapped('user_id').ids
        employee_ids = [eid for eid in employee_ids if eid != approver.id]
        if not employee_ids:
            return {'pending_requests': [], 'history_requests': []}

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        pending = self.sudo().search([
            ('employee_id', 'in', employee_ids),
            ('state', '=', 'รออนุมัติ'),
        ], order='create_date asc')
        history = self.sudo().search([
            ('employee_id', 'in', employee_ids),
            ('state', 'in', ('อนุมัติ', 'ไม่อนุมัติ')),
            ('approved_at', '>=', fields.Datetime.now() - timedelta(days=7)),
        ], order='approved_at desc')
        return {
            'pending_requests': [rec._as_dict(base_url) for rec in pending],
            'history_requests': [rec._as_dict(base_url) for rec in history],
        }

    @api.model
    def api_approve_action(self, approver_id, request_id, action, reason=None,
                           new_state=None):
        approver = self.env['employee.salary'].sudo().browse(int(approver_id))
        if not approver.exists():
            raise UserError('ไม่พบข้อมูลผู้ใช้')
        record = self.sudo().browse(int(request_id))
        if not record.exists():
            raise UserError('ไม่พบคำขอเพิ่มเวลา')

        allowed_ids = self.env['approver.relations'].sudo().search(
            [('approver_user_id', '=', approver.id)]).mapped('user_id').ids
        if record.employee_id.id not in allowed_ids:
            raise UserError('คุณไม่มีสิทธิ์อนุมัติคำขอของพนักงานคนนี้')

        if action == 'approve':
            record.action_approve(approver=approver)
            return {'message': 'ดำเนินการอนุมัติคำขอเพิ่มเวลาเรียบร้อยแล้ว'}
        if action == 'disapprove':
            record.action_disapprove(reason=reason, approver=approver)
            return {'message': 'ดำเนินการไม่อนุมัติคำขอเรียบร้อยแล้ว'}
        if action == 'edit_status':
            if new_state == 'ยกเลิก':
                record.action_cancel()
            elif new_state == 'อนุมัติ':
                record.action_approve(approver=approver)
            elif new_state == 'ไม่อนุมัติ':
                record.action_disapprove(reason=reason, approver=approver)
            elif new_state == 'รออนุมัติ':
                record.action_reset_to_pending()
            else:
                raise UserError('สถานะไม่ถูกต้อง: %s' % new_state)
            return {'message': 'แก้ไขสถานะเรียบร้อยแล้ว'}
        raise UserError('Invalid action.')

    @api.model
    def api_cancel(self, request_id, employee_id=None):
        record = self.sudo().browse(int(request_id))
        if not record.exists():
            raise UserError('ไม่พบคำขอที่ต้องการยกเลิก')
        if employee_id and record.employee_id.id != int(employee_id):
            raise UserError('ไม่สามารถยกเลิกคำขอของพนักงานคนอื่นได้')
        record.action_cancel()
        return {'message': 'ยกเลิกคำขอเรียบร้อยแล้ว'}

    # ------------------------------------------------------------------
    # Helper สำหรับ payroll (โมดูลเงินเดือนเรียกใช้)
    # ------------------------------------------------------------------
    @api.model
    def get_approved_totals(self, employee, date_from, date_to, exclude_codes=()):
        """ยอดรวมที่อนุมัติแล้วในช่วงรอบ แยกตามฟิลด์รายได้ในสลิป

        คืน dict {payroll_income_field: ยอดรวม} — เอนจินเงินเดือนเอาไปเขียนลงสลิป
        โดยไม่ต้องรู้ว่ามีประเภทอะไรบ้าง (เดิม hardcode ไว้ใน INCOME_REASON_MAP)
        """
        logs = self.sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'อนุมัติ'),
            ('work_date', '>=', date_from),
            ('work_date', '<=', date_to),
        ])
        exclude_codes = set(exclude_codes or ())
        totals = {}
        for log in logs:
            reason = log.reason_type_id
            # ประเภทที่สลิปมีช่องแยกของตัวเองอยู่แล้ว (เช่น ค่าตัวนักแสดง)
            # ต้องกันไม่ให้นับซ้ำ
            if reason.code and reason.code in exclude_codes:
                continue
            field_name = reason.payroll_income_field
            if not field_name:
                continue
            totals[field_name] = totals.get(field_name, 0.0) + (log.amount or 0.0)
        return totals
