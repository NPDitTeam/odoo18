# -*- coding: utf-8 -*-
"""แสดงบนหน้า "ข้อมูลพนักงาน" ว่าใครลงกะแล้วหรือยัง

สำคัญกับการตรวจสอบ เพราะพนักงานที่ยังไม่ลงกะจะถูก **ข้าม** ทั้งการคิดสาย/ขาดงาน
ในเงินเดือน และการออกใบเตือน โดยไม่มีอะไรฟ้อง — เอนจินคำนวณจะ log แล้วคืนค่าว่าง
ไปเฉย ๆ ทำให้คนที่ตกหล่นดูเหมือนไม่เคยสาย ไม่เคยขาด

ทำเป็นฟิลด์คำนวณพร้อม ``search`` แทนการเก็บค่าจริง เพราะแหล่งความจริงคือ
``hr.work.schedule`` (มี unique ต่อพนักงาน 1 คน 1 กะ) การเก็บซ้ำจะหลุดกันได้
"""
from odoo import _, fields, models
from odoo.exceptions import UserError


class EmployeeSalaryWorkSchedule(models.Model):
    _inherit = 'employee.salary'

    work_schedule_id = fields.Many2one(
        'hr.work.schedule', string='ตารางกะ',
        compute='_compute_work_schedule_state')
    work_schedule_state = fields.Selection([
        ('checkin', 'ลงกะแล้ว'),
        ('no_checkin', 'ลงกะแล้ว (ไม่ต้องเช็คอิน)'),
        ('unset', 'ยังไม่ลงกะ'),
    ], string='สถานะตารางกะ',
        compute='_compute_work_schedule_state',
        search='_search_work_schedule_state',
        help='ยังไม่ลงกะ = ระบบไม่รู้ว่าวันไหนคือวันทำงานของคนนี้\n'
             'จะถูกข้ามทั้งการคิดสาย/ขาดงานในเงินเดือน และการออกใบเตือน')

    def _compute_work_schedule_state(self):
        found = {}
        if self.ids:
            schedules = self.env['hr.work.schedule'].sudo().search(
                [('employee_id', 'in', self.ids)])
            found = {s.employee_id.id: s for s in schedules}
        for rec in self:
            sched = found.get(rec.id)
            rec.work_schedule_id = sched.id if sched else False
            if not sched:
                rec.work_schedule_state = 'unset'
            else:
                rec.work_schedule_state = (
                    'no_checkin' if sched.category == 'no_checkin' else 'checkin')

    def _search_work_schedule_state(self, operator, value):
        """ให้กรองได้ทั้งที่เป็นฟิลด์คำนวณข้ามโมเดล"""
        with_schedule = self.env['hr.work.schedule'].sudo().search(
            []).mapped('employee_id').ids
        values = value if isinstance(value, (list, tuple)) else [value]
        wants_unset = 'unset' in values
        if operator in ('=', 'in'):
            want_set = not wants_unset
        elif operator in ('!=', 'not in'):
            want_set = wants_unset
        else:
            raise UserError(_('ตัวกรองสถานะตารางกะรองรับเฉพาะ = และ != เท่านั้น'))
        return [('id', 'in' if want_set else 'not in', with_schedule)]
