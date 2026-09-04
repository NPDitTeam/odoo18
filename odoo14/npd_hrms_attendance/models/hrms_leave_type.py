# -*- coding: utf-8 -*-
"""ประเภทการลา + สิทธิ์คงเหลือรายบุคคล

Odoo 14 เก็บสิทธิ์การลาเป็น "คอลัมน์ตายตัว 8 ประเภท" บนโมเดล hr.leave.type.custom
(leave_vacation_total, leave_vacation_total_remaining, ...) เพิ่มประเภทใหม่ต้องแก้โค้ด
ทั้ง Odoo และ PHP — ที่นี่แยกเป็นสองโมเดล:

    hrms.leave.type     ประเภทการลา (ข้อมูลหลัก ตั้งเองได้รายบริษัท)
    hrms.leave.balance  สิทธิ์คงเหลือ = พนักงาน × ประเภท × ปี

``code`` ของประเภทตรงกับคีย์เดิมที่แอปใช้ (leave_vacation, leave_sick, ...)
ทำให้ API คืน JSON รูปแบบเดิมได้เป๊ะ ๆ ทั้งที่ข้างในเป็นข้อมูลหลักแล้ว

เจ้าของค่า (สำคัญ — เดิมเคยเขียนทับกันบ่อย):
  "ทั้งหมด" (total)     = สิทธิ์ตามอายุงาน → ระบบคำนวณให้ อัปเดตได้ทุกวัน
  "คงเหลือ" (remaining) = ผลของการยื่นลาจริง → แตะเฉพาะตอนยื่น/ยกเลิก/ขึ้นปีใหม่
"""
import logging

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class HrmsLeaveType(models.Model):
    _name = 'hrms.leave.type'
    _description = 'ประเภทการลา'
    _order = 'sequence, id'

    # ไม่ใส่ translate=True: ชื่อประเภทเป็นข้อมูลหลักที่ผู้ใช้กรอกเอง (เหมือนชื่อสาขา)
    # ไม่ใช่ข้อความบน UI — และถ้าแปลได้ คอลัมน์จะเป็น jsonb ทำให้ฟิลด์ related
    # แบบ store=True ที่ดึงชื่อนี้ไปเก็บ (leave_type_name) ชนิดไม่ตรงกันจน write ล้ม
    name = fields.Char(string='ชื่อประเภทการลา', required=True)
    code = fields.Char(
        string='รหัสอ้างอิง', required=True,
        help='รหัสที่แอปใช้อ้างถึงประเภทนี้ เช่น leave_vacation — '
             'ห้ามแก้หลังเริ่มใช้งานแล้ว เพราะแอปเวอร์ชันเก่าอ้างรหัสนี้อยู่')
    sequence = fields.Integer(string='ลำดับ', default=10)
    active = fields.Boolean(string='ใช้งาน', default=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)

    days_default = fields.Integer(
        string='สิทธิ์ตั้งต้น (วัน/ปี)', default=0,
        help='จำนวนวันที่ได้รับเมื่อครบเงื่อนไขอายุงาน')
    is_paid = fields.Boolean(
        string='ได้รับค่าจ้าง', default=True,
        help='ใช้ตอนคำนวณเงินเดือน — ประเภทที่ไม่ได้รับค่าจ้างจะถูกหักเงิน')
    requires_attachment = fields.Boolean(
        string='ต้องแนบเอกสาร',
        help='เช่น ลาป่วยที่ต้องมีใบรับรองแพทย์ — แอปจะบังคับให้แนบไฟล์')

    eligible_after_months = fields.Integer(
        string='ได้สิทธิ์เมื่อทำงานครบ (เดือน)', default=0)
    eligible_after_years = fields.Integer(
        string='ได้สิทธิ์เมื่อทำงานครบ (ปี)', default=0)
    prorate_first_year = fields.Boolean(
        string='ปันส่วนปีแรกตามเดือนที่เหลือ',
        help='ปีปฏิทินที่เพิ่งครบอายุงาน จะได้สิทธิ์ตามสัดส่วนเดือนที่เหลือ (ปัดลง) '
             'เช่น ลาพักร้อน 7 วัน ครบรอบเดือน ก.ค. → ได้ 7×6/12 = 3 วัน')
    reset_on_new_year = fields.Boolean(
        string='รีเซ็ตสิทธิ์ทุกวันที่ 1 ม.ค.', default=True)

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'รหัสอ้างอิงนี้ถูกใช้ไปแล้วในบริษัทนี้'),
    ]

    @api.constrains('code')
    def _check_code(self):
        for rec in self:
            if not rec.code or not rec.code.replace('_', '').isalnum():
                raise ValidationError(
                    'รหัสอ้างอิงต้องเป็นตัวอักษรอังกฤษ ตัวเลข หรือ _ เท่านั้น (%s)'
                    % rec.code)

    def _entitled_days(self, start_date, today):
        """สิทธิ์ที่พนักงานคนนี้ควรได้ ณ วันที่ today ตามอายุงาน"""
        self.ensure_one()
        if not start_date:
            return 0
        if self.eligible_after_months:
            if today < start_date + relativedelta(months=self.eligible_after_months):
                return 0
        anniversary = start_date
        if self.eligible_after_years:
            anniversary = start_date + relativedelta(years=self.eligible_after_years)
            if today < anniversary:
                return 0
        if self.prorate_first_year and today.year == anniversary.year:
            remaining_months = 12 - anniversary.month + 1
            return self.days_default * remaining_months // 12
        return self.days_default


class HrmsLeaveBalance(models.Model):
    _name = 'hrms.leave.balance'
    _description = 'สิทธิ์การลาคงเหลือ'
    _order = 'employee_id, leave_type_id'
    _rec_name = 'leave_type_id'

    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True,
        ondelete='cascade', index=True)
    employee_code = fields.Char(
        string='รหัสพนักงาน', related='employee_id.employee_code',
        store=True, readonly=True, index=True)
    leave_type_id = fields.Many2one(
        'hrms.leave.type', string='ประเภทการลา', required=True, ondelete='cascade')
    leave_type_code = fields.Char(
        string='รหัสประเภท', related='leave_type_id.code', store=True, readonly=True)
    year = fields.Integer(
        string='ปี', required=True,
        default=lambda self: fields.Date.context_today(self).year, index=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', related='employee_id.company_id',
        store=True, readonly=True)

    total = fields.Integer(string='ทั้งหมด (วัน)', default=0)
    remaining = fields.Integer(string='คงเหลือ (วัน)', default=0)
    used = fields.Integer(string='ใช้ไป (วัน)', compute='_compute_used', store=True)

    _sql_constraints = [
        ('emp_type_year_uniq', 'unique(employee_id, leave_type_id, year)',
         'มีรายการสิทธิ์การลาของพนักงานคนนี้ ประเภทนี้ ปีนี้อยู่แล้ว'),
    ]

    @api.depends('total', 'remaining')
    def _compute_used(self):
        for rec in self:
            rec.used = max(0, (rec.total or 0) - (rec.remaining or 0))

    # ------------------------------------------------------------------
    # หัก / คืนสิทธิ์ — จุดเดียวที่แตะ remaining ทั้งระบบ
    # ------------------------------------------------------------------
    def _deduct(self, days):
        """หักสิทธิ์ตอนยื่นใบลา — raise ถ้าสิทธิ์ไม่พอ"""
        self.ensure_one()
        if days <= 0:
            return
        if days > self.remaining:
            raise UserError(
                'จำนวนวันลาเกินสิทธิ์ที่เหลืออยู่ (%d วัน)' % self.remaining)
        self.remaining -= days

    def _revert(self, days):
        """คืนสิทธิ์ตอนยกเลิก/ไม่อนุมัติ — คืนได้ไม่เกิน total (กันคงเหลือเกินสิทธิ์)

        เป็นกฎเดียวกับที่ PHP ทำใน cancel_leave_request / approve_leave_screen
        """
        self.ensure_one()
        if days <= 0:
            return
        self.remaining = min(self.total, self.remaining + days)

    # ------------------------------------------------------------------
    # หา/สร้างรายการสิทธิ์
    # ------------------------------------------------------------------
    @api.model
    def _get_or_create(self, employee, leave_type, year=None):
        year = year or fields.Date.context_today(self).year
        balance = self.sudo().search([
            ('employee_id', '=', employee.id),
            ('leave_type_id', '=', leave_type.id),
            ('year', '=', year),
        ], limit=1)
        if balance:
            return balance
        today = fields.Date.context_today(self)
        entitled = leave_type._entitled_days(employee.start_date, today)
        return self.sudo().create({
            'employee_id': employee.id,
            'leave_type_id': leave_type.id,
            'year': year,
            'total': entitled,
            'remaining': entitled,
        })

    @api.model
    def _sync_employee(self, employee, year=None, reset_remaining=False):
        """สร้าง/อัปเดตรายการสิทธิ์ทุกประเภทของพนักงานคนนี้

        อัปเดต "ทั้งหมด" เสมอ (สิทธิ์ตามอายุงานเปลี่ยนได้ทุกวัน)
        แตะ "คงเหลือ" เฉพาะเมื่อ reset_remaining=True (ขึ้นปีใหม่ / สร้างครั้งแรก)
        หรือเมื่อเพิ่งได้สิทธิ์ใหม่ (total เดิม 0 → วันนี้มีสิทธิ์แล้ว)
        """
        year = year or fields.Date.context_today(self).year
        today = fields.Date.context_today(self)
        company = employee.company_id or self.env.company
        types = self.env['hrms.leave.type'].sudo().search(
            [('company_id', '=', company.id)])
        for leave_type in types:
            balance = self._get_or_create(employee, leave_type, year)
            entitled = leave_type._entitled_days(employee.start_date, today)
            vals = {'total': entitled}
            newly_entitled = balance.total == 0 and entitled > 0
            if reset_remaining or newly_entitled:
                vals['remaining'] = entitled
            balance.write(vals)

    @api.model
    def _find(self, employee, code, year=None):
        """หารายการสิทธิ์จากรหัสประเภท (เช่น 'leave_vacation')"""
        year = year or fields.Date.context_today(self).year
        company = employee.company_id or self.env.company
        leave_type = self.env['hrms.leave.type'].sudo().search([
            ('code', '=', code), ('company_id', '=', company.id)], limit=1)
        if not leave_type:
            return self.browse()
        return self._get_or_create(employee, leave_type, year)

    @api.model
    def _find_by_name(self, employee, type_name, year=None):
        """หารายการสิทธิ์จากชื่อไทยของประเภท (แอปส่งชื่อมา ไม่ใช่รหัส)"""
        if not type_name:
            return self.browse()
        company = employee.company_id or self.env.company
        leave_type = self.env['hrms.leave.type'].sudo().search([
            ('name', '=', type_name.strip()), ('company_id', '=', company.id)], limit=1)
        if not leave_type:
            return self.browse()
        return self._get_or_create(employee, leave_type, year)

    # ------------------------------------------------------------------
    # Cron: อัปเดตสิทธิ์รายวัน
    # ------------------------------------------------------------------
    @api.model
    def _cron_update_leave_entitlements(self):
        """อัปเดตสิทธิ์ตามอายุงานทุกวัน และรีเซ็ตทั้งหมดวันที่ 1 ม.ค.

        ทำเฉพาะพนักงานที่ยัง active หรือลาออกในรอบจ่ายปัจจุบัน (ยังต้องคิดเงินเดือน)

        Odoo 14 ต้อง pull "คงเหลือ" จาก PHP ก่อนทุกครั้งเพื่อไม่ให้ทับค่าที่แอปหักไป
        — ตอนนี้แอปหักที่ Odoo โดยตรงแล้ว ขั้นตอน pull จึงหายไปทั้งหมด
        """
        today = fields.Date.context_today(self)
        is_new_year = today.month == 1 and today.day == 1
        Employee = self.env['employee.salary'].sudo()
        updated = 0

        for company in self.env['res.company'].sudo().search([]):
            cutoff = company.hrms_cutoff_start_day or 25
            if today.day >= cutoff:
                cyc_year, cyc_month = today.year, today.month
            elif today.month == 1:
                cyc_year, cyc_month = today.year - 1, 12
            else:
                cyc_year, cyc_month = today.year, today.month - 1
            import calendar
            last_day = calendar.monthrange(cyc_year, cyc_month)[1]
            cycle_start = fields.Date.to_date(
                '%04d-%02d-%02d' % (cyc_year, cyc_month, min(cutoff, last_day)))

            employees = Employee.search([
                ('company_id', '=', company.id),
                '|',
                ('status', '=', 'active'),
                '&', ('resign_date', '!=', False), ('resign_date', '>=', cycle_start),
            ])
            for employee in employees:
                try:
                    self._sync_employee(
                        employee, year=today.year, reset_remaining=is_new_year)
                    updated += 1
                except Exception as exc:
                    # ข้ามคนที่พัง ไม่ให้ล้มทั้ง cron
                    _logger.warning(
                        'อัปเดตสิทธิ์การลาล้มเหลว emp=%s: %s',
                        employee.employee_code, exc)
        _logger.info(
            'Leave entitlement cron: อัปเดต %s คน (new_year=%s)', updated, is_new_year)
        return True

    # ------------------------------------------------------------------
    # API สำหรับแอป
    # ------------------------------------------------------------------
    @api.model
    def api_get_allowance(self, employee_code, year=None):
        """สิทธิ์การลาทุกประเภทของพนักงาน

        คืน dict แบน ๆ คีย์เดียวกับ get_leave_allowance.php เดิม:
            {code}_used            → ชื่อไทยของประเภท (ของเดิมเก็บ label ไว้ที่คีย์นี้)
            {code}_total_remaining → คงเหลือ
            {code}_total           → ทั้งหมด
        """
        employee = self.env['employee.salary']._find_by_code(employee_code)
        if not employee:
            return {}
        year = int(year) if year else fields.Date.context_today(self).year
        self._sync_employee(employee, year=year)
        balances = self.sudo().search([
            ('employee_id', '=', employee.id), ('year', '=', year)])
        result = {}
        for balance in balances:
            code = balance.leave_type_code
            result['%s_used' % code] = balance.leave_type_id.name or ''
            result['%s_total_remaining' % code] = balance.remaining
            result['%s_total' % code] = balance.total
        return result

    @api.model
    def api_check_allowance(self, employee_code, leave_type_code, year=None):
        """สิทธิ์ของประเภทเดียว — รูปแบบเดียวกับ check_leave_allowance.php"""
        employee = self.env['employee.salary']._find_by_code(employee_code)
        if not employee:
            return {}
        balance = self._find(employee, leave_type_code, year)
        if not balance:
            return {}
        return {'total': balance.total, 'remaining': balance.remaining}
