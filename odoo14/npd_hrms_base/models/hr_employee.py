# -*- coding: utf-8 -*-
"""ผูก hr.employee มาตรฐานของ Odoo กลับมาที่บัตรพนักงาน HRMS

มีไว้เพื่อให้เปิดจากฝั่ง Odoo HR แล้วกระโดดมาดูข้อมูล HRMS ได้ และเพื่อให้
โมดูลอื่นของ Odoo (Expense / Fleet / Attendance) ใช้ hr.employee ตามปกติ
โดยที่ข้อมูลเงินเดือนยังอยู่ที่ employee.salary ที่เดียว
"""
from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    hrms_employee_id = fields.Many2one(
        'employee.salary', string='บัตรพนักงาน (HRMS)',
        compute='_compute_hrms_employee_id', store=True, readonly=True)
    hrms_employee_code = fields.Char(
        string='รหัสพนักงาน (HRMS)',
        related='hrms_employee_id.employee_code', readonly=True)

    @api.depends('name')
    def _compute_hrms_employee_id(self):
        """หา employee.salary ที่ชี้กลับมาที่ hr.employee นี้

        ทิศทางความจริงคือ employee.salary.hr_employee_id → hr.employee
        ฝั่งนี้เป็นแค่ทางลัดกลับ จึงคำนวณจากอีกฝั่งเสมอ
        """
        Salary = self.env['employee.salary'].sudo()
        mapped = {
            rec.hr_employee_id.id: rec.id
            for rec in Salary.search([('hr_employee_id', 'in', self.ids)])
        }
        for employee in self:
            employee.hrms_employee_id = mapped.get(employee.id, False)

    def action_open_hrms_employee(self):
        self.ensure_one()
        if not self.hrms_employee_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'บัตรพนักงาน (HRMS)',
            'res_model': 'employee.salary',
            'res_id': self.hrms_employee_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
