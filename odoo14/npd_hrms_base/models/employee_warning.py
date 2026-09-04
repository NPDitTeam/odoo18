# -*- coding: utf-8 -*-
"""ใบเตือนพนักงาน

พอร์ตจาก Odoo 14 — เปลี่ยน branch_id ไปชี้ res.branch และเพิ่มเมธอด api_*
ที่แอปเรียกอยู่แล้ว (api_get_warning_count / api_get_warnings_by_employee_code)
ให้อยู่ในโมเดลนี้ ไม่ต้องผ่าน PHP
"""
from odoo import models, fields, api


class EmployeeWarning(models.Model):
    _name = 'employee.warning'
    _description = 'ใบเตือนพนักงาน'
    _inherit = ['mail.thread']
    _rec_name = 'employee_id'
    _order = 'employee_code'

    _sql_constraints = [
        ('employee_uniq', 'unique(employee_id)',
         'ไม่สามารถเพิ่มชื่อพนักงานซ้ำได้ ! พนักงานคนนี้มีใบเตือนอยู่แล้ว'),
    ]

    employee_id = fields.Many2one(
        'employee.salary', string='ชื่อพนักงาน', required=True, ondelete='restrict')
    employee_code = fields.Char(
        string='รหัสพนักงาน', related='employee_id.employee_code',
        store=True, readonly=True, index=True)
    firstname = fields.Char(
        string='ชื่อ', related='employee_id.firstname', store=True, readonly=True)
    lastname = fields.Char(
        string='นามสกุล', related='employee_id.lastname', store=True, readonly=True)
    position_id = fields.Many2one(
        'hr.position.custom', string='ตำแหน่ง',
        related='employee_id.position_id', store=True, readonly=True)
    branch_id = fields.Many2one(
        'res.branch', string='สาขา',
        related='employee_id.branch_id', store=True, readonly=True)
    department_id = fields.Many2one(
        'hr.department.custom', string='แผนก',
        related='employee_id.department_id', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท',
        related='employee_id.company_id', store=True, readonly=True)

    warning_line_ids = fields.One2many(
        'employee.warning.line', 'warning_id', string='รายการใบเตือน')
    warning_count = fields.Integer(
        string='จำนวนใบเตือน', compute='_compute_warning_count', store=True)
    last_warning_date = fields.Date(
        string='ใบเตือนล่าสุด', compute='_compute_warning_count', store=True)
    note = fields.Text(string='หมายเหตุ')

    @api.depends('warning_line_ids', 'warning_line_ids.warning_date')
    def _compute_warning_count(self):
        for rec in self:
            rec.warning_count = len(rec.warning_line_ids)
            dates = rec.warning_line_ids.mapped('warning_date')
            rec.last_warning_date = max(dates) if dates else False

    @api.onchange('warning_line_ids')
    def _onchange_warning_line_ids(self):
        """ให้เลขครั้งเรียง 1, 2, 3, ... ใหม่ทุกครั้งที่เพิ่ม/ลบบรรทัด"""
        for idx, line in enumerate(self.warning_line_ids, start=1):
            line.warning_number = idx

    # ------------------------------------------------------------------
    # API สำหรับแอป (คงลายเซ็นเดิมที่แอปเรียกอยู่)
    # ------------------------------------------------------------------
    @api.model
    def api_get_warning_count(self, employee_code):
        if not employee_code:
            return 0
        warning = self.sudo().search(
            [('employee_code', '=', str(employee_code))], limit=1)
        return warning.warning_count if warning else 0

    @api.model
    def api_get_warnings_by_employee_code(self, employee_code):
        if not employee_code:
            return []
        warning = self.sudo().search(
            [('employee_code', '=', str(employee_code))], limit=1)
        if not warning:
            return []
        return [{
            'id': line.id,
            'warning_number': idx,
            'warning_date': line.warning_date.isoformat() if line.warning_date else '',
            'subject': line.subject or '',
            'warning_type': line.warning_type or '',
            'warning_type_label': dict(
                line._fields['warning_type'].selection).get(line.warning_type, ''),
            'description': line.description or '',
            'has_attachment': bool(line.attachment),
            'attachment_filename': line.attachment_filename or '',
        } for idx, line in enumerate(
            warning.warning_line_ids.sorted('warning_date'), start=1)]


class EmployeeWarningLine(models.Model):
    _name = 'employee.warning.line'
    _description = 'รายการใบเตือนพนักงาน'
    _order = 'warning_number asc, id asc'

    warning_id = fields.Many2one(
        'employee.warning', string='ใบเตือนพนักงาน', required=True, ondelete='cascade')
    employee_code = fields.Char(
        related='warning_id.employee_code', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', related='warning_id.company_id', store=True, readonly=True)

    warning_date = fields.Date(
        string='วันที่ออกใบเตือน', required=True, default=fields.Date.context_today)
    subject = fields.Char(string='เรื่องที่โดนเตือน', required=True)
    warning_type = fields.Selection([
        ('verbal', 'ตักเตือนด้วยวาจา'),
        ('written', 'ตักเตือนเป็นหนังสือ'),
    ], string='ประเภทใบเตือน', required=True, default='verbal')
    warning_number = fields.Integer(
        string='จำนวนครั้งออกใบเตือน', default=1,
        help='ระบบจะกำหนดเลขครั้งให้อัตโนมัติตามลำดับ')
    warning_number_display = fields.Char(
        string='ครั้งที่', compute='_compute_warning_number_display')
    sequence = fields.Integer(string='ลำดับ', default=10)
    attachment = fields.Binary(string='ไฟล์แนบใบเตือน', attachment=True)
    attachment_filename = fields.Char(string='ชื่อไฟล์แนบ')
    description = fields.Text(string='รายละเอียดเพิ่มเติม')

    @api.depends('warning_number', 'warning_id.warning_line_ids',
                 'warning_id.warning_line_ids.warning_number')
    def _compute_warning_number_display(self):
        for rec in self:
            # ใช้ตำแหน่งในรายการเป็นหลัก เพื่อให้เลขถูกต้องแม้ warning_number
            # ยังไม่ถูกอัปเดต (เช่น ตอนกำลังแก้ฟอร์มอยู่)
            position = 0
            if rec.warning_id:
                lines = list(rec.warning_id.warning_line_ids)
                if rec in lines:
                    position = lines.index(rec) + 1
            position = position or rec.warning_number or 0
            rec.warning_number_display = 'ครั้งที่ %s' % position if position else ''

    @api.model_create_multi
    def create(self, vals_list):
        """ตั้งเลขครั้งอัตโนมัติตอนสร้างเรคคอร์ดใหม่ (กรณีสร้างผ่าน API)"""
        for vals in vals_list:
            if not vals.get('warning_number') and vals.get('warning_id'):
                existing = self.search_count(
                    [('warning_id', '=', vals['warning_id'])])
                vals['warning_number'] = existing + 1
        return super().create(vals_list)
