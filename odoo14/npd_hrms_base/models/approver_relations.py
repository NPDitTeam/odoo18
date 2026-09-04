# -*- coding: utf-8 -*-
"""สายอนุมัติ — พนักงานคนนี้ให้ใครอนุมัติ (ลา / เพิ่มเวลา / เบิก)

พอร์ตจาก Odoo 14 ตัด PHP sync ออก และเพิ่มเมธอดที่แอปใช้ตัดสินว่า
ผู้ใช้คนนี้เห็นเมนู "อนุมัติ" ไหม และอนุมัติของใครได้บ้าง
(เดิมฝั่ง PHP คำนวณให้ใน menu_data_test.php)
"""
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ApproverRelations(models.Model):
    _name = 'approver.relations'
    _description = 'สายอนุมัติ'
    _rec_name = 'user_id'
    _order = 'user_id'

    user_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='บริษัท', related='user_id.company_id',
        store=True, readonly=True)
    department_id = fields.Many2one(
        'hr.department.custom', string='แผนก',
        related='user_id.department_id', readonly=True)
    branch_id = fields.Many2one(
        'res.branch', string='สาขา', related='user_id.branch_id', readonly=True)
    position_id = fields.Many2one(
        'hr.position.custom', string='ตำแหน่งผู้อนุมัติ')
    approver_user_id = fields.Many2one(
        'employee.salary', string='รายชื่อผู้อนุมัติ',
        domain="[('position_id', '=', position_id)]")
    sequence = fields.Integer(
        string='ลำดับการอนุมัติ', default=10,
        help='เลขน้อยอนุมัติก่อน — ใช้เมื่อมีผู้อนุมัติหลายชั้น')

    employee_code = fields.Char(
        related='user_id.employee_code', string='รหัสพนักงาน',
        store=True, readonly=True)
    approver_employee_code = fields.Char(
        related='approver_user_id.employee_code', string='รหัสผู้อนุมัติ',
        store=True, readonly=True)
    approver_name = fields.Char(
        related='approver_user_id.full_name', string='ชื่อผู้อนุมัติ',
        store=True, readonly=True)

    _sql_constraints = [
        ('user_position_unique', 'unique(user_id, position_id)',
         'สายอนุมัติของพนักงานคนนี้ในตำแหน่งนี้มีอยู่แล้ว'),
    ]

    @api.constrains('user_id', 'approver_user_id')
    def _check_unique_approver(self):
        for rec in self:
            if rec.user_id and rec.user_id == rec.approver_user_id:
                raise ValidationError('พนักงานไม่สามารถเป็นผู้อนุมัติของตัวเองได้')

    # ------------------------------------------------------------------
    # API สำหรับแอป
    # ------------------------------------------------------------------
    @api.model
    def api_get_approvers(self, employee_code):
        """รายชื่อผู้อนุมัติของพนักงานคนนี้ เรียงตามลำดับการอนุมัติ"""
        if not employee_code:
            return []
        emp = self.env['employee.salary'].sudo().search(
            [('employee_code', '=', str(employee_code))], limit=1)
        if not emp:
            return []
        relations = self.sudo().search(
            [('user_id', '=', emp.id)], order='sequence, id')
        return [{
            'sequence': rel.sequence,
            'position': rel.position_id.name or '',
            'approver_code': rel.approver_employee_code or '',
            'approver_name': rel.approver_name or '',
        } for rel in relations if rel.approver_user_id]

    @api.model
    def api_get_subordinate_codes(self, approver_code):
        """รหัสพนักงานทุกคนที่ผู้ใช้คนนี้เป็นผู้อนุมัติให้

        แอปใช้ตัดสินว่าจะแสดงเมนู "อนุมัติการลา" / "อนุมัติเพิ่มเวลา" ไหม
        และใช้เป็นตัวกรองรายการที่ดึงมาแสดง
        """
        if not approver_code:
            return []
        approver = self.env['employee.salary'].sudo().search(
            [('employee_code', '=', str(approver_code))], limit=1)
        if not approver:
            return []
        relations = self.sudo().search([('approver_user_id', '=', approver.id)])
        return sorted({
            rel.employee_code for rel in relations if rel.employee_code
        })
