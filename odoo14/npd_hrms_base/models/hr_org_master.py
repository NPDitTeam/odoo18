# -*- coding: utf-8 -*-
"""แผนก / ตำแหน่ง ของระบบ HR

คงชื่อโมเดลเดิมจาก Odoo 14 (hr.department.custom, hr.position.custom) ไว้
เพราะแอป HR และเอนจิน payroll อ้างชื่อฟิลด์ department_id / position_id อยู่แล้ว
— เปลี่ยนแค่ตัด PHP sync ออก และเพิ่มลิงก์ไปโมเดล HR มาตรฐานของ Odoo
(hr.department / hr.job) เผื่อใช้ฟีเจอร์ฝั่ง Odoo ร่วมด้วย

**ไม่ผูกกับบริษัท** — แผนกและตำแหน่งใช้ชุดเดียวกันทั้งองค์กร เช่น "ฝ่ายบัญชี"
หรือ "หัวหน้าสาขา" มีความหมายเหมือนกันไม่ว่าจะอยู่บริษัทไหน การแยกตามบริษัท
จะทำให้ต้องสร้างชื่อซ้ำหลายชุดและรายงานข้ามบริษัทจัดกลุ่มไม่ได้
(การแยกข้อมูลจริงอยู่ที่ระดับพนักงานและสาขาอยู่แล้ว)
"""
from odoo import models, fields, api


class HrDepartmentCustom(models.Model):
    _name = 'hr.department.custom'
    _description = 'แผนก (HRMS)'
    _order = 'sequence, name'

    name = fields.Char(string='ชื่อแผนก', required=True)
    sequence = fields.Integer(string='ลำดับ', default=10)
    is_active = fields.Boolean(string='ใช้งาน', default=True)
    active = fields.Boolean(string='แสดงในรายการ', default=True)
    department_id = fields.Many2one(
        'hr.department', string='แผนก (Odoo HR)',
        help='ผูกกับแผนกมาตรฐานของ Odoo เพื่อใช้ฟีเจอร์ HR ทั่วไปร่วมกัน')
    employee_count = fields.Integer(
        string='จำนวนพนักงาน', compute='_compute_employee_count')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'ชื่อแผนกนี้มีอยู่แล้ว'),
    ]

    def _compute_employee_count(self):
        Employee = self.env['employee.salary'].sudo()
        data = Employee._read_group(
            [('department_id', 'in', self.ids)], ['department_id'], ['__count'])
        mapped = {dept.id: count for dept, count in data}
        for rec in self:
            rec.employee_count = mapped.get(rec.id, 0)

    @api.model
    def _find_or_create_by_name(self, name):
        """หาแผนกจากชื่อ ถ้าไม่มีให้สร้าง — ใช้ตอนนำเข้าข้อมูลเดิม"""
        if not name:
            return False
        name = name.strip()
        rec = self.sudo().search([('name', '=', name)], limit=1)
        if not rec:
            rec = self.sudo().create({'name': name})
        return rec.id


class HrPositionCustom(models.Model):
    _name = 'hr.position.custom'
    _description = 'ตำแหน่ง (HRMS)'
    _order = 'sequence, name'

    name = fields.Char(string='ชื่อตำแหน่ง', required=True)
    sequence = fields.Integer(string='ลำดับ', default=10)
    is_active = fields.Boolean(string='ใช้งาน', default=True)
    active = fields.Boolean(string='แสดงในรายการ', default=True)
    department_id = fields.Many2one('hr.department.custom', string='แผนกหลัก')
    job_id = fields.Many2one(
        'hr.job', string='ตำแหน่ง (Odoo HR)',
        help='ผูกกับตำแหน่งมาตรฐานของ Odoo')

    # ธงสำหรับสายงานที่ payroll ต้องแยกสูตร
    is_sales = fields.Boolean(
        string='เป็นตำแหน่งฝ่ายขาย',
        help='ใช้ตัดสินว่าคนนี้เข้าเงื่อนไขค่าคอมมิชชั่น Sales')
    is_driver = fields.Boolean(
        string='เป็นตำแหน่งพนักงานขับรถ',
        help='ใช้ตัดสินว่าคนนี้ได้ค่าเที่ยว/เบี้ยเลี้ยงคนขับจากงานขนส่ง/เช่า')
    is_branch_manager = fields.Boolean(
        string='เป็นหัวหน้าสาขา',
        help='ใช้ตัดสินสิทธิ์อนุมัติและค่าคอมระดับสาขา')

    employee_count = fields.Integer(
        string='จำนวนพนักงาน', compute='_compute_employee_count')

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'ชื่อตำแหน่งนี้มีอยู่แล้ว'),
    ]

    def _compute_employee_count(self):
        Employee = self.env['employee.salary'].sudo()
        data = Employee._read_group(
            [('position_id', 'in', self.ids)], ['position_id'], ['__count'])
        mapped = {pos.id: count for pos, count in data}
        for rec in self:
            rec.employee_count = mapped.get(rec.id, 0)

    @api.model
    def _find_or_create_by_name(self, name):
        if not name:
            return False
        name = name.strip()
        rec = self.sudo().search([('name', '=', name)], limit=1)
        if not rec:
            rec = self.sudo().create({'name': name})
        return rec.id
