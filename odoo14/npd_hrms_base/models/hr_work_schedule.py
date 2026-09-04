# -*- coding: utf-8 -*-
"""ตารางงาน (วันทำงาน + เวลาเข้า-ออกแต่ละวัน)

พอร์ตตรงจาก Odoo 14 — เพิ่มวันอาทิตย์ (เดิมมีแค่ จ.–ส.) เพราะงานปล่อยเช่า/ขนส่ง
มีกะวันอาทิตย์ และเพิ่มเมธอด api_get_schedule ให้แอปเรียกผ่าน JSON-RPC ได้ตรง
"""
from odoo import models, fields, api

DAYS = [
    ('mon', 'จันทร์', 1),
    ('tue', 'อังคาร', 2),
    ('wed', 'พุธ', 3),
    ('thu', 'พฤหัสบดี', 4),
    ('fri', 'ศุกร์', 5),
    ('sat', 'เสาร์', 6),
    ('sun', 'อาทิตย์', 7),
]

DEFAULT_START = 8.0
DEFAULT_END = 17.0


def float_to_time_str(value):
    """8.5 → '08:30'"""
    value = value or 0.0
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    return '%02d:%02d' % (hours, minutes)


class HrWorkSchedule(models.Model):
    _name = 'hr.work.schedule'
    _description = 'ตารางงาน (เช็คอิน & กะทำงาน)'
    _rec_name = 'employee_id'

    _sql_constraints = [
        ('employee_id_uniq', 'unique(employee_id)',
         'พนักงานคนนี้มีตารางงานอยู่แล้ว'),
    ]

    employee_id = fields.Many2one(
        'employee.salary', string='ชื่อพนักงาน', required=True, ondelete='cascade')
    employee_code = fields.Char(
        string='รหัสพนักงาน', related='employee_id.employee_code',
        store=True, readonly=True)
    position_id = fields.Many2one(
        'hr.position.custom', string='ตำแหน่ง',
        related='employee_id.position_id', store=True, readonly=True)
    department_id = fields.Many2one(
        'hr.department.custom', string='แผนก',
        related='employee_id.department_id', store=True, readonly=True)
    branch_id = fields.Many2one(
        'res.branch', string='สาขา',
        related='employee_id.branch_id', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท',
        related='employee_id.company_id', store=True, readonly=True)

    category = fields.Selection([
        ('checkin', 'เช็คอิน'),
        ('no_checkin', 'ไม่ต้องเช็คอิน'),
    ], string='หมวดหมู่', default='no_checkin', required=True)

    work_mon = fields.Boolean('วันจันทร์', default=True)
    work_tue = fields.Boolean('วันอังคาร', default=True)
    work_wed = fields.Boolean('วันพุธ', default=True)
    work_thu = fields.Boolean('วันพฤหัสบดี', default=True)
    work_fri = fields.Boolean('วันศุกร์', default=True)
    work_sat = fields.Boolean('วันเสาร์', default=True)
    work_sun = fields.Boolean('วันอาทิตย์', default=False)

    mon_shift_start = fields.Float('จันทร์ เริ่ม', default=DEFAULT_START)
    mon_shift_end = fields.Float('จันทร์ เลิก', default=DEFAULT_END)
    tue_shift_start = fields.Float('อังคาร เริ่ม', default=DEFAULT_START)
    tue_shift_end = fields.Float('อังคาร เลิก', default=DEFAULT_END)
    wed_shift_start = fields.Float('พุธ เริ่ม', default=DEFAULT_START)
    wed_shift_end = fields.Float('พุธ เลิก', default=DEFAULT_END)
    thu_shift_start = fields.Float('พฤหัส เริ่ม', default=DEFAULT_START)
    thu_shift_end = fields.Float('พฤหัส เลิก', default=DEFAULT_END)
    fri_shift_start = fields.Float('ศุกร์ เริ่ม', default=DEFAULT_START)
    fri_shift_end = fields.Float('ศุกร์ เลิก', default=DEFAULT_END)
    sat_shift_start = fields.Float('เสาร์ เริ่ม', default=DEFAULT_START)
    sat_shift_end = fields.Float('เสาร์ เลิก', default=DEFAULT_END)
    sun_shift_start = fields.Float('อาทิตย์ เริ่ม', default=0.0)
    sun_shift_end = fields.Float('อาทิตย์ เลิก', default=0.0)

    @api.onchange('category')
    def _onchange_category(self):
        """ไม่ต้องเช็คอิน → ล้างวันทำงานและเวลาทั้งหมด / กลับมาเช็คอิน → คืนค่า จ.–ส. 8–17"""
        for rec in self:
            checkin = rec.category == 'checkin'
            for code, _label, _weekday in DAYS:
                is_workday = checkin and code != 'sun'
                rec[f'work_{code}'] = is_workday
                rec[f'{code}_shift_start'] = DEFAULT_START if is_workday else 0.0
                rec[f'{code}_shift_end'] = DEFAULT_END if is_workday else 0.0

    @api.onchange('work_mon', 'work_tue', 'work_wed', 'work_thu',
                  'work_fri', 'work_sat', 'work_sun')
    def _onchange_workdays(self):
        """ติ๊กวันไหนเข้า → คืนเวลา 8–17, ติ๊กออก → เวลาเป็น 0

        Odoo 14 เขียนแยกเป็น 6 เมธอด — รวมเป็นตัวเดียวเพราะพฤติกรรมเหมือนกันหมด
        """
        for rec in self:
            for code, _label, _weekday in DAYS:
                if rec[f'work_{code}']:
                    if not rec[f'{code}_shift_end']:
                        rec[f'{code}_shift_start'] = DEFAULT_START
                        rec[f'{code}_shift_end'] = DEFAULT_END
                else:
                    rec[f'{code}_shift_start'] = 0.0
                    rec[f'{code}_shift_end'] = 0.0

    # ------------------------------------------------------------------
    # Helper ที่ payroll / API ใช้ร่วมกัน
    # ------------------------------------------------------------------
    def _shift_for_weekday(self, weekday):
        """weekday แบบ ISO (1=จันทร์ ... 7=อาทิตย์) → (is_workday, start, end)"""
        self.ensure_one()
        for code, _label, iso in DAYS:
            if iso == weekday:
                return (self[f'work_{code}'],
                        self[f'{code}_shift_start'],
                        self[f'{code}_shift_end'])
        return (False, 0.0, 0.0)

    def _as_dict(self):
        """รูปแบบเดียวกับที่ /api/work_schedule เดิมส่งให้แอป"""
        self.ensure_one()
        days = []
        for code, label, iso in DAYS:
            if not self[f'work_{code}']:
                continue
            start = self[f'{code}_shift_start']
            end = self[f'{code}_shift_end']
            days.append({
                'day': code,
                'day_label': label,
                'weekday': iso,
                'shift_start': float_to_time_str(start),
                'shift_end': float_to_time_str(end),
                'shift_start_float': start,
                'shift_end_float': end,
            })
        return {
            'employee_code': self.employee_code or '',
            'category': self.category or '',
            'days': days,
        }

    @api.model
    def api_get_schedule(self, employee_code):
        """เรียกจากแอป: callKw('hr.work.schedule', 'api_get_schedule', [code])"""
        if not employee_code:
            return {}
        schedule = self.sudo().search(
            [('employee_code', '=', str(employee_code))], limit=1)
        return schedule._as_dict() if schedule else {}
