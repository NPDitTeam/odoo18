# -*- coding: utf-8 -*-
"""รหัสพนักงานบนผู้ใช้ระบบ

รายงานค่าคอมต้องรู้ว่าเซลล์คนไหนเป็น "Sales สำนักงานใหญ่" ซึ่งรายชื่อเก็บเป็น
รหัสพนักงานฝั่งระบบบุคคล ส่วนใบแจ้งหนี้ผูกกับ ``res.users`` จึงต้องมีสะพาน
เชื่อมสองฝั่ง

ไม่เก็บลงฐาน เพราะทะเบียนพนักงานเป็นแหล่งข้อมูลจริงอยู่แล้ว
การเก็บซ้ำมีแต่จะไม่ตรงกันเมื่อมีการแก้รหัสพนักงาน
"""
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    employee_code = fields.Char(
        string='รหัสพนักงาน', compute='_compute_employee_code',
        search='_search_employee_code',
        help='อ่านจากทะเบียนพนักงานที่ผูกกับผู้ใช้รายนี้')

    def _compute_employee_code(self):
        Employee = self.env['employee.salary'].sudo()
        by_user = {}
        for emp in Employee.search([('user_id', 'in', self.ids)]):
            by_user.setdefault(emp.user_id.id, emp.employee_code)
        for user in self:
            user.employee_code = by_user.get(user.id, False)

    @api.model
    def _search_employee_code(self, operator, value):
        employees = self.env['employee.salary'].sudo().search(
            [('employee_code', operator, value)])
        return [('id', 'in', employees.mapped('user_id').ids)]
