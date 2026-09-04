# -*- coding: utf-8 -*-
"""ผูกบัตรพนักงานกับคนขับ

``vehicle.driver`` มีฟิลด์ ``employee_code`` อยู่แล้วเป็นตัวเชื่อมกับระบบ HR
โมดูลนี้ทำให้ความสัมพันธ์นั้นเห็นได้จากทั้งสองฝั่ง และเตือนเมื่อรหัสไม่ตรงกับใคร
— เพราะถ้าจับคู่ไม่ติด ค่าเที่ยวจะเงียบหายไปจากสลิปโดยไม่มีใครรู้
"""
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class EmployeeSalaryRental(models.Model):
    _inherit = 'employee.salary'

    driver_id = fields.Many2one(
        'vehicle.driver', string='คนขับ (งานขนส่ง)',
        compute='_compute_driver_id', store=True, readonly=True,
        help='จับคู่อัตโนมัติจากรหัสพนักงานที่กรอกไว้ในทะเบียนคนขับ')
    is_driver = fields.Boolean(
        string='เป็นพนักงานขับรถ', compute='_compute_driver_id', store=True)
    booking_count = fields.Integer(
        string='งานขนส่ง', compute='_compute_booking_count')

    @api.depends('employee_code')
    def _compute_driver_id(self):
        Driver = self.env['vehicle.driver'].sudo()
        for rec in self:
            driver = Driver.search(
                [('employee_code', '=', rec.employee_code)], limit=1
            ) if rec.employee_code else Driver.browse()
            rec.driver_id = driver.id or False
            rec.is_driver = bool(driver)

    def _compute_booking_count(self):
        Booking = self.env['vehicle.booking'].sudo()
        for rec in self:
            rec.booking_count = Booking.search_count(
                [('driver_id', '=', rec.driver_id.id)]) if rec.driver_id else 0

    def action_view_bookings(self):
        """งานขนส่งทั้งหมดของพนักงานคนนี้"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'งานขนส่ง — %s' % (self.full_name or ''),
            'res_model': 'vehicle.booking',
            'view_mode': 'list,form',
            'domain': [('driver_id', '=', self.driver_id.id)],
        }


class VehicleDriverHrms(models.Model):
    _inherit = 'vehicle.driver'

    hrms_employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน (HRMS)',
        compute='_compute_hrms_employee', store=True, readonly=True)
    hrms_matched = fields.Boolean(
        string='จับคู่กับพนักงานได้', compute='_compute_hrms_employee', store=True,
        help='ถ้าไม่ติ๊ก แปลว่ารหัสพนักงานที่กรอกไว้ไม่ตรงกับใครในระบบ HR '
             'ค่าเที่ยวของคนขับคนนี้จะไม่เข้าสลิปเงินเดือน')

    @api.depends('employee_code')
    def _compute_hrms_employee(self):
        Employee = self.env['employee.salary'].sudo()
        for rec in self:
            employee = Employee.search(
                [('employee_code', '=', rec.employee_code)], limit=1
            ) if rec.employee_code else Employee.browse()
            rec.hrms_employee_id = employee.id or False
            rec.hrms_matched = bool(employee)
            if rec.employee_code and not employee:
                _logger.warning(
                    '[RENTAL HR] คนขับ %s รหัส %s ไม่ตรงกับพนักงานคนไหนในระบบ HR '
                    '→ ค่าเที่ยวจะไม่เข้าสลิป',
                    rec.name, rec.employee_code)

    # ------------------------------------------------------------------
    # employee.salary.driver_id เป็น stored compute ที่ depends แค่ employee_code
    # ของตัวเอง จึงไม่รู้ตัวเมื่อมีการสร้าง/แก้ทะเบียนคนขับทีหลัง
    # ต้องสั่งคำนวณฝั่งพนักงานใหม่เอง ไม่งั้นค่าเที่ยวจะไม่เข้าสลิปจนกว่าจะแก้บัตรพนักงาน
    # ------------------------------------------------------------------
    def _sync_employee_link(self, extra_codes=()):
        codes = {code for code in self.mapped('employee_code') if code}
        codes.update(code for code in extra_codes if code)
        if not codes:
            return
        employees = self.env['employee.salary'].sudo().search(
            [('employee_code', 'in', list(codes))])
        if employees:
            employees.invalidate_recordset(['driver_id', 'is_driver'])
            employees.modified(['employee_code'])

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_employee_link()
        return records

    def write(self, vals):
        # เก็บรหัสเดิมไว้ด้วย เผื่อย้ายรหัสไปคนอื่น คนเดิมต้องถูกปลดลิงก์
        previous_codes = list(self.mapped('employee_code'))
        res = super().write(vals)
        if 'employee_code' in vals:
            self._sync_employee_link(previous_codes)
        return res

    def unlink(self):
        codes = list(self.mapped('employee_code'))
        res = super().unlink()
        self.env['vehicle.driver']._sync_employee_link(codes)
        return res
