# -*- coding: utf-8 -*-
"""ใบลา

ย้ายตรรกะทั้งหมดจาก PHP (submit_leave_request / approve_leave_screen /
cancel_leave_request) มาไว้ในโมเดล เพื่อให้หน้าเว็บ Odoo กับแอปใช้กฎชุดเดียวกัน

วงจรสิทธิ์วันลา (ยกมาจาก PHP ตรง ๆ):
  ยื่น      → ตรวจสิทธิ์ แล้ว "หัก" ทันที (ยังไม่รออนุมัติผ่านก่อน)
  แก้ไข     → คืนสิทธิ์ของเดิมก่อน แล้วตรวจ/หักตามจำนวนใหม่
  อนุมัติ    → ไม่แตะสิทธิ์ (หักไปตั้งแต่ตอนยื่นแล้ว)
  ไม่อนุมัติ → คืนสิทธิ์
  ยกเลิก    → คืนสิทธิ์ (ใบที่อนุมัติแล้วยกเลิกได้เฉพาะที่ยังไม่ถึงวันลา)
"""
import logging
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

LEAVE_STATES = [
    ('รออนุมัติ', 'รออนุมัติ'),
    ('อนุมัติ', 'อนุมัติ'),
    ('ไม่อนุมัติ', 'ไม่อนุมัติ'),
    ('ยกเลิก', 'ยกเลิก'),
]

OPEN_STATES = ('รออนุมัติ', 'อนุมัติ')


class HrAttendanceBranchLeave(models.Model):
    _name = 'hr.attendance.branch.leave'
    _description = 'การลา'
    _inherit = ['mail.thread']
    _order = 'create_date desc'
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

    leave_type_id = fields.Many2one(
        'hrms.leave.type', string='ประเภทการลา', required=True,
        ondelete='restrict', tracking=True)
    leave_type_name = fields.Char(
        string='ประเภทการลา (ชื่อ)', related='leave_type_id.name',
        store=True, readonly=True)

    leave_start_date = fields.Date(string='วันที่ลาเริ่มต้น', required=True, tracking=True)
    start_time = fields.Char(string='เวลาที่ลาเริ่มต้น', required=True, default='08:00')
    leave_end_date = fields.Date(string='วันที่ลาสิ้นสุด', required=True, tracking=True)
    end_time = fields.Char(string='เวลาที่ลาสิ้นสุด', required=True, default='17:00')
    leave_days = fields.Integer(
        string='จำนวนวันลา', compute='_compute_leave_days', store=True,
        help='นับรวมวันเริ่มและวันสิ้นสุด เช่น 25–27 = 3 วัน')

    note = fields.Text(string='หมายเหตุผู้ใช้')
    reason = fields.Char(string='หมายเหตุผู้อนุมัติ')
    state = fields.Selection(
        LEAVE_STATES, string='สถานะ', default='รออนุมัติ',
        required=True, tracking=True, index=True)

    approved_by = fields.Many2one(
        'employee.salary', string='ผู้อนุมัติ', readonly=True)
    approved_at = fields.Datetime(string='วันที่อนุมัติ', readonly=True)

    attachment = fields.Binary(string='ไฟล์แนบ', attachment=True)
    filename = fields.Char(string='ชื่อไฟล์')

    display_summary = fields.Char(
        string='รายการ', compute='_compute_display_summary', store=True)

    # จำนวนวันที่ "หักสิทธิ์ไปแล้ว" — เก็บไว้เพื่อคืนได้ตรงจำนวนแม้ผู้ใช้แก้วันที่ภายหลัง
    deducted_days = fields.Integer(
        string='หักสิทธิ์ไปแล้ว (วัน)', default=0, readonly=True, copy=False)
    deducted_type_id = fields.Many2one(
        'hrms.leave.type', string='ประเภทที่หักสิทธิ์', readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Compute / Constraints
    # ------------------------------------------------------------------
    @api.depends('leave_start_date', 'leave_end_date')
    def _compute_leave_days(self):
        for rec in self:
            if rec.leave_start_date and rec.leave_end_date:
                if rec.leave_end_date < rec.leave_start_date:
                    rec.leave_days = 1
                else:
                    rec.leave_days = (rec.leave_end_date - rec.leave_start_date).days + 1
            else:
                rec.leave_days = 0

    @api.depends('username', 'leave_type_name', 'leave_start_date', 'leave_end_date')
    def _compute_display_summary(self):
        for rec in self:
            parts = [rec.username or '', rec.leave_type_name or '']
            if rec.leave_start_date:
                parts.append(rec.leave_start_date.strftime('%d/%m/%Y'))
            rec.display_summary = ' - '.join(part for part in parts if part)

    @api.constrains('leave_start_date', 'leave_end_date')
    def _check_dates(self):
        for rec in self:
            if (rec.leave_start_date and rec.leave_end_date
                    and rec.leave_end_date < rec.leave_start_date):
                raise ValidationError('วันที่สิ้นสุดการลาต้องไม่ก่อนวันที่เริ่มลา')

    @api.constrains('leave_type_id', 'attachment')
    def _check_attachment_required(self):
        for rec in self:
            if (rec.leave_type_id.requires_attachment and not rec.attachment
                    and rec.state == 'รออนุมัติ'):
                raise ValidationError(
                    'ประเภทการลา "%s" ต้องแนบเอกสารประกอบ' % rec.leave_type_id.name)

    # ------------------------------------------------------------------
    # จัดการสิทธิ์วันลา
    # ------------------------------------------------------------------
    def _balance(self, leave_type=None):
        """รายการสิทธิ์ของใบลานี้ (อิงปีของวันเริ่มลา)"""
        self.ensure_one()
        leave_type = leave_type or self.leave_type_id
        if not leave_type:
            return self.env['hrms.leave.balance']
        year = (self.leave_start_date or fields.Date.context_today(self)).year
        return self.env['hrms.leave.balance']._get_or_create(
            self.employee_id, leave_type, year)

    def _apply_deduction(self):
        """คืนสิทธิ์ที่หักไว้เดิม (ถ้ามี) แล้วหักตามจำนวน/ประเภทปัจจุบัน

        เขียนเป็นขั้นตอนเดียวเพื่อให้ทั้งตอนสร้างและตอนแก้ไขใช้ทางเดินเดียวกัน
        — PHP แยกโค้ดสองชุดแล้วเคยหลุดเคส "เปลี่ยนประเภทการลาตอนแก้ไข"
        """
        self.ensure_one()
        self._revert_deduction()
        days = self.leave_days
        if days <= 0:
            return
        balance = self._balance()
        if not balance:
            raise UserError(
                'ยังไม่ได้ตั้งค่าสิทธิ์การลาประเภท "%s" ให้พนักงานคนนี้'
                % (self.leave_type_id.name or ''))
        balance._deduct(days)
        self.sudo().write({
            'deducted_days': days,
            'deducted_type_id': self.leave_type_id.id,
        })

    def _revert_deduction(self):
        """คืนสิทธิ์ตามจำนวน/ประเภทที่ "หักไปจริง" ไม่ใช่ค่าปัจจุบันบนฟอร์ม"""
        self.ensure_one()
        if not self.deducted_days or not self.deducted_type_id:
            return
        balance = self._balance(self.deducted_type_id)
        if balance:
            balance._revert(self.deducted_days)
        self.sudo().write({'deducted_days': 0, 'deducted_type_id': False})

    # ------------------------------------------------------------------
    # CRUD — หักสิทธิ์อัตโนมัติ ไม่ว่าจะสร้างจากแอปหรือหน้าเว็บ
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.state == 'รออนุมัติ':
                record._apply_deduction()
        return records

    def write(self, vals):
        res = super().write(vals)
        # แก้วันที่/ประเภท ขณะยังรออนุมัติ → คำนวณสิทธิ์ใหม่
        recalc_fields = {'leave_start_date', 'leave_end_date', 'leave_type_id'}
        if recalc_fields & set(vals) and not self.env.context.get('skip_leave_deduction'):
            for record in self:
                if record.state == 'รออนุมัติ':
                    record.with_context(skip_leave_deduction=True)._apply_deduction()
        return res

    def unlink(self):
        for record in self:
            if record.state in OPEN_STATES:
                record._revert_deduction()
        return super().unlink()

    # ------------------------------------------------------------------
    # ปุ่มดำเนินการ
    # ------------------------------------------------------------------
    def action_approve(self, approver=None):
        for rec in self:
            if rec.state != 'รออนุมัติ':
                raise UserError('อนุมัติได้เฉพาะใบลาที่สถานะ "รออนุมัติ"')
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
                raise UserError('ไม่อนุมัติได้เฉพาะใบลาที่สถานะ "รออนุมัติ"')
            rec._revert_deduction()
            rec.write({
                'state': 'ไม่อนุมัติ',
                'reason': reason or 'ไม่มีเหตุผล',
                'approved_by': (approver or rec._current_employee()).id or False,
                'approved_at': fields.Datetime.now(),
            })
        return True

    def action_cancel(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state not in OPEN_STATES:
                raise UserError(
                    'ยกเลิกได้เฉพาะใบลาที่สถานะ "รออนุมัติ" หรือ "อนุมัติ"')
            if rec.state == 'อนุมัติ':
                # ใบที่อนุมัติแล้วยกเลิกได้เฉพาะที่ยังไม่ถึงวันลา
                if rec.leave_end_date < today:
                    raise UserError(
                        'ไม่สามารถยกเลิกได้ เนื่องจากวันที่สิ้นสุดการลาผ่านไปแล้ว')
                if rec.leave_start_date < today:
                    raise UserError(
                        'ไม่สามารถยกเลิกได้ เนื่องจากวันลาเริ่มไปแล้ว')
            rec._revert_deduction()
            rec.write({'state': 'ยกเลิก'})
        return True

    def action_reset_to_pending(self):
        """ดึงกลับมาเป็นรออนุมัติ (ใช้เมื่อเจ้าหน้าที่กดผิด) — หักสิทธิ์ใหม่"""
        for rec in self:
            if rec.state == 'รออนุมัติ':
                continue
            rec.write({
                'state': 'รออนุมัติ',
                'reason': False,
                'approved_by': False,
                'approved_at': False,
            })
            rec._apply_deduction()
        return True

    def _current_employee(self):
        """บัตรพนักงานของผู้ใช้ Odoo ที่กำลังทำรายการ (ถ้ามี)"""
        return self.env['employee.salary'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)

    # ------------------------------------------------------------------
    # API สำหรับแอป
    # ------------------------------------------------------------------
    def _as_dict(self, base_url=''):
        """รูปแบบเดียวกับที่ leave_requests.php ส่งให้แอป

        คีย์ ``leave_statr_time`` สะกดผิดมาตั้งแต่ตาราง MySQL เดิม —
        คงไว้เพราะแอปที่ผู้ใช้ติดตั้งอยู่อ่านคีย์นี้
        """
        self.ensure_one()
        approver = self.approved_by
        return {
            'id': self.id,
            'user_id': self.employee_id.id,
            'employee_code': self.employee_code or '',
            'username': self.username or '',
            'firstname': self.employee_id.firstname or '',
            'lastname': self.employee_id.lastname or '',
            'leave_start_date': self.leave_start_date.isoformat() if self.leave_start_date else '',
            'leave_statr_time': self.start_time or '',
            'leave_start_time': self.start_time or '',
            'leave_end_date': self.leave_end_date.isoformat() if self.leave_end_date else '',
            'leave_end_time': self.end_time or '',
            'leave_days': self.leave_days,
            'leave_type': self.leave_type_name or '',
            'note': self.note or '',
            'state': self.state or '',
            'reason': self.reason or '',
            'file_path': (
                '%s/api/hrms/v1/leave/attachment/%s' % (base_url.rstrip('/'), self.id)
                if self.attachment else ''),
            'approved_by': approver.id if approver else None,
            'approver_firstname': approver.firstname if approver else '',
            'approver_lastname': approver.lastname if approver else '',
            'approved_at': self.approved_at.strftime('%Y-%m-%d %H:%M:%S') if self.approved_at else '',
            'created_at': self.create_date.strftime('%Y-%m-%d %H:%M:%S') if self.create_date else '',
            'department': self.department_id.name or '',
            'position': self.position_id.name or '',
            'branch': self.branch_id.name or '',
            'company': self.company_id.name or '',
        }

    @api.model
    def api_submit(self, employee_id, leave_type, leave_start_date, start_time,
                   leave_end_date, end_time, note=None, request_id=None,
                   attachment=None, filename=None, clear_attachment=False):
        """ยื่น/แก้ไขใบลาจากแอป — แทน submit_leave_request_test.php

        ``leave_type`` รับเป็นชื่อไทย (แอปส่งชื่อมา) หรือรหัสประเภทก็ได้
        """
        employee = self.env['employee.salary'].sudo().browse(int(employee_id))
        if not employee.exists():
            raise UserError('ไม่พบข้อมูลพนักงาน')

        leave_type_rec = self._resolve_leave_type(employee, leave_type)
        vals = {
            'employee_id': employee.id,
            'leave_type_id': leave_type_rec.id,
            'leave_start_date': leave_start_date,
            'start_time': start_time,
            'leave_end_date': leave_end_date,
            'end_time': end_time,
            'note': note or False,
        }
        if attachment:
            vals.update({'attachment': attachment, 'filename': filename or 'attachment'})
        elif clear_attachment:
            vals.update({'attachment': False, 'filename': False})

        if request_id:
            record = self.sudo().browse(int(request_id))
            if not record.exists() or record.employee_id != employee:
                raise UserError('ไม่พบคำขอลาที่ต้องการแก้ไข')
            if record.state != 'รออนุมัติ':
                raise UserError('ไม่สามารถแก้ไขคำขอได้เนื่องจากสถานะไม่ใช่ "รออนุมัติ"')
            record.write(vals)
            return {'id': record.id, 'message': 'แก้ไขคำขอลาเรียบร้อยแล้ว'}

        record = self.sudo().create(vals)
        return {'id': record.id, 'message': 'ส่งคำขอลาเรียบร้อยแล้ว, กรุณารอการอนุมัติ'}

    @api.model
    def _resolve_leave_type(self, employee, leave_type):
        """รับได้ทั้งชื่อไทย รหัสอ้างอิง และ id — แอปเวอร์ชันต่างกันส่งไม่เหมือนกัน"""
        LeaveType = self.env['hrms.leave.type'].sudo()
        company = employee.company_id or self.env.company
        domain_base = [('company_id', '=', company.id)]
        if isinstance(leave_type, int):
            record = LeaveType.browse(leave_type)
            if record.exists():
                return record
        else:
            text = str(leave_type or '').strip()
            record = LeaveType.search(domain_base + [('name', '=', text)], limit=1)
            if not record:
                record = LeaveType.search(domain_base + [('code', '=', text)], limit=1)
            if record:
                return record
        raise UserError('ไม่พบประเภทการลา "%s"' % leave_type)

    @api.model
    def api_get_history(self, employee_id, limit=7, month=None, year=None):
        """ประวัติการลา — ไม่ส่งเดือน/ปี = ล่าสุด N รายการ (พฤติกรรมเดิมของหน้าแรก)"""
        domain = [('employee_id', '=', int(employee_id))]
        if month and year:
            import calendar
            month, year = int(month), int(year)
            last_day = calendar.monthrange(year, month)[1]
            domain += [
                ('leave_start_date', '>=',
                 fields.Date.to_date('%04d-%02d-01' % (year, month))),
                ('leave_start_date', '<=',
                 fields.Date.to_date('%04d-%02d-%02d' % (year, month, last_day))),
            ]
            limit = None
        records = self.sudo().search(
            domain, order='create_date desc', limit=limit or None)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        return [rec._as_dict(base_url) for rec in records]

    @api.model
    def api_get_approval_queue(self, approver_id):
        """รายการรออนุมัติ + ประวัติ 7 วัน สำหรับผู้อนุมัติ

        แทน approve_leave_screen_test.php — กรองด้วย approver.relations เหมือนเดิม
        และไม่รวมใบลาของตัวผู้อนุมัติเอง
        """
        approver = self.env['employee.salary'].sudo().browse(int(approver_id))
        if not approver.exists():
            raise UserError('ไม่พบข้อมูลผู้ใช้')

        relations = self.env['approver.relations'].sudo().search(
            [('approver_user_id', '=', approver.id)])
        employee_ids = relations.mapped('user_id').ids
        if not employee_ids:
            return {'pending_requests': [], 'history_requests': []}
        employee_ids = [eid for eid in employee_ids if eid != approver.id]

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
        """อนุมัติ / ไม่อนุมัติ / แก้สถานะ — แทน POST ของ approve_leave_screen_test.php"""
        approver = self.env['employee.salary'].sudo().browse(int(approver_id))
        if not approver.exists():
            raise UserError('ไม่พบข้อมูลผู้ใช้')

        record = self.sudo().browse(int(request_id))
        if not record.exists():
            raise UserError('ไม่พบคำขอลา')

        allowed_ids = self.env['approver.relations'].sudo().search(
            [('approver_user_id', '=', approver.id)]).mapped('user_id').ids
        if record.employee_id.id not in allowed_ids:
            raise UserError('คุณไม่มีสิทธิ์อนุมัติคำขอของพนักงานคนนี้')

        if action == 'approve':
            record.action_approve(approver=approver)
            return {'message': 'ดำเนินการอนุมัติคำขอลาเรียบร้อยแล้ว'}
        if action == 'disapprove':
            record.action_disapprove(reason=reason, approver=approver)
            return {'message': 'ดำเนินการไม่อนุมัติคำขอและคืนสิทธิ์เรียบร้อยแล้ว'}
        if action == 'edit_status':
            if not new_state:
                raise UserError('สถานะใหม่เป็นค่าว่าง')
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
        """ยกเลิกใบลา — แทน cancel_leave_request_test.php"""
        record = self.sudo().browse(int(request_id))
        if not record.exists():
            raise UserError('ไม่พบคำขอที่สามารถยกเลิกได้')
        if employee_id and record.employee_id.id != int(employee_id):
            raise UserError('ไม่สามารถยกเลิกคำขอของพนักงานคนอื่นได้')
        record.action_cancel()
        return {'message': 'ยกเลิกคำขอเรียบร้อยแล้ว'}
