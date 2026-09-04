# -*- coding: utf-8 -*-
"""รอบทำเงินเดือน — สร้างสลิปทั้งบริษัททีเดียว แล้วคุมสถานะรวม"""
import calendar
import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

THAI_MONTHS = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]

MONTH_SELECTION = [(str(i), THAI_MONTHS[i - 1]) for i in range(1, 13)]


class PayrollPeriod(models.Model):
    _name = 'payroll.period'
    _description = 'รอบทำเงินเดือน'
    _inherit = ['mail.thread']
    _order = 'year desc, month desc'
    _rec_name = 'display_name'

    month = fields.Integer(
        string='เดือน', required=True,
        default=lambda self: fields.Date.context_today(self).month)
    year = fields.Integer(
        string='ปี', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)

    cutoff_start_day = fields.Integer(
        string='วันเริ่มรอบ', required=True,
        default=lambda self: self.env.company.hrms_cutoff_start_day or 25,
        help='วันที่ของเดือนก่อนหน้าที่รอบเริ่ม')
    cutoff_end_day = fields.Integer(
        string='วันตัดรอบ', required=True,
        default=lambda self: (self.env.company.hrms_cutoff_start_day or 25) - 1,
        help='วันที่ของเดือนนี้ที่รอบสิ้นสุด')
    date_from = fields.Date(
        string='ตั้งแต่วันที่', compute='_compute_dates', store=True)
    date_to = fields.Date(
        string='ถึงวันที่', compute='_compute_dates', store=True)
    payment_date = fields.Date(string='วันที่จ่ายเงิน')

    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('computed', 'คำนวณแล้ว'),
        ('approved', 'อนุมัติแล้ว'),
        ('paid', 'จ่ายแล้ว'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='draft', required=True, tracking=True)

    salary_ids = fields.One2many(
        'payroll.salary', 'period_id', string='รายการเงินเดือน')
    employee_count = fields.Integer(
        string='จำนวนพนักงาน', compute='_compute_totals', store=True)
    total_gross = fields.Float(
        string='รวมรายได้', compute='_compute_totals', store=True)
    total_deduction = fields.Float(
        string='รวมรายการหัก', compute='_compute_totals', store=True)
    total_net = fields.Float(
        string='รวมเงินสุทธิ', compute='_compute_totals', store=True)

    _sql_constraints = [
        ('period_uniq', 'unique(month, year, company_id)',
         'มีรอบทำเงินเดือนของเดือน/ปีนี้ในบริษัทนี้อยู่แล้ว'),
    ]

    @api.depends('month', 'year')
    def _compute_display_name(self):
        for rec in self:
            if 1 <= (rec.month or 0) <= 12:
                rec.display_name = '%s %s' % (THAI_MONTHS[rec.month - 1], rec.year)
            else:
                rec.display_name = _('รอบทำเงินเดือนใหม่')

    @api.depends('month', 'year', 'cutoff_start_day', 'cutoff_end_day')
    def _compute_dates(self):
        for rec in self:
            try:
                rec.date_from, rec.date_to = rec._cycle_window()
            except (TypeError, ValueError):
                rec.date_from = rec.date_to = False

    @api.depends('salary_ids.total_gross', 'salary_ids.total_deduction',
                 'salary_ids.net_salary')
    def _compute_totals(self):
        for rec in self:
            rec.employee_count = len(rec.salary_ids)
            rec.total_gross = sum(rec.salary_ids.mapped('total_gross'))
            rec.total_deduction = sum(rec.salary_ids.mapped('total_deduction'))
            rec.total_net = sum(rec.salary_ids.mapped('net_salary'))

    @api.constrains('month', 'cutoff_start_day', 'cutoff_end_day')
    def _check_values(self):
        for rec in self:
            if not 1 <= rec.month <= 12:
                raise UserError('เดือนต้องอยู่ระหว่าง 1–12')
            if not 1 <= rec.cutoff_start_day <= 31:
                raise UserError('วันเริ่มรอบต้องอยู่ระหว่าง 1–31')
            if not 1 <= rec.cutoff_end_day <= 31:
                raise UserError('วันตัดรอบต้องอยู่ระหว่าง 1–31')

    # ------------------------------------------------------------------
    def _cycle_window(self):
        """ช่วงวันของรอบนี้ — วันเริ่มรอบของเดือนก่อน ถึงวันตัดรอบของเดือนนี้

        เช่น เริ่ม 25 ตัด 24 เดือน 5/2026 → 25/04/2026 ถึง 24/05/2026
        """
        self.ensure_one()
        year, month = int(self.year), int(self.month)
        last_curr = calendar.monthrange(year, month)[1]
        date_to = date(year, month, min(self.cutoff_end_day, last_curr))
        prev = date(year, month, 1) - relativedelta(months=1)
        last_prev = calendar.monthrange(prev.year, prev.month)[1]
        date_from = date(prev.year, prev.month, min(self.cutoff_start_day, last_prev))
        return date_from, date_to

    def _eligible_employees(self):
        """พนักงานที่ต้องคิดเงินเดือนรอบนี้

        รวมคนที่ลาออกแล้วแต่วันลาออกยังอยู่ในรอบ (ต้องจ่ายรอบสุดท้าย)
        """
        self.ensure_one()
        date_from, date_to = self._cycle_window()
        return self.env['employee.salary'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('auto_payroll', '=', True),
            '|',
            ('status', '=', 'active'),
            '&', ('resign_date', '!=', False), ('resign_date', '>=', date_from),
        ])

    @api.model
    def _is_eligible_employee(self, employee, cycle_start, cycle_end):
        """พนักงานคนนี้อยู่ในรอบ [cycle_start, cycle_end] ไหม

        แยกออกมาเป็นเมธอดระดับโมเดล เพราะงานอื่นที่ไม่มีเรคคอร์ดรอบ
        (เช่น การออกใบเตือนอัตโนมัติ) ต้องใช้เกณฑ์ "ใครอยู่ในรอบ" ชุดเดียวกัน
        จะได้ไม่ออกใบเตือนให้คนที่ลาออกไปแล้วหรือยังไม่เริ่มงาน

        วันเริ่มงาน/วันลาออกมีอำนาจเหนือสถานะ เผื่อกรณีลืมปรับสถานะหลังลาออก
        """
        if employee.start_date and employee.start_date > cycle_end:
            return False
        if employee.resign_date:
            return employee.resign_date >= cycle_start
        return employee.status == 'active'

    # ------------------------------------------------------------------
    # ปุ่มดำเนินการ
    # ------------------------------------------------------------------
    def action_generate(self):
        """สร้างรายการเงินเดือนให้พนักงานทุกคนในรอบนี้ (ข้ามคนที่มีแล้ว)"""
        Salary = self.env['payroll.salary']
        for rec in self:
            if rec.state not in ('draft', 'computed'):
                raise UserError('สร้างรายการได้เฉพาะรอบที่ยังเป็นร่างหรือคำนวณแล้ว')
            existing = set(rec.salary_ids.mapped('employee_id').ids)
            created = 0
            for employee in rec._eligible_employees():
                if employee.id in existing:
                    continue
                Salary.create({
                    'period_id': rec.id,
                    'employee_id': employee.id,
                    'month': rec.month,
                    'year': str(rec.year),
                    'company_id': rec.company_id.id,
                    'cutoff_day': rec.cutoff_end_day,
                    'payment_date': rec.payment_date or False,
                })
                created += 1
            _logger.info('[PAYROLL PERIOD] %s: สร้างรายการใหม่ %d คน',
                         rec.display_name, created)
            rec.state = 'computed'
        return True

    def action_recompute(self):
        """คำนวณใหม่ทั้งรอบ — ใช้เมื่อแก้ข้อมูลลงเวลา/ใบลาย้อนหลัง"""
        for rec in self:
            rec.salary_ids.action_recalculate()
        return True

    def action_approve(self):
        """อนุมัติรอบ = ยืนยันสลิปทุกใบในรอบด้วย

        ถ้าปล่อยสลิปเป็นร่างไว้ พนักงานจะเปิดสลิปในแอปไม่ได้ (แอปแสดงเฉพาะ
        สลิปที่ยืนยันแล้ว) ทั้งที่ยอดถูกนำไปออก ภ.ง.ด.1 เรียบร้อยแล้ว
        """
        for rec in self:
            if not rec.salary_ids:
                raise UserError('ยังไม่มีรายการเงินเดือนในรอบนี้')
            rec.state = 'approved'
            to_confirm = rec.salary_ids.filtered(
                lambda s: s.state == 'draft' and s.line_ids)
            if to_confirm:
                to_confirm.action_confirm()
            incomplete = rec.salary_ids.filtered(lambda s: not s.line_ids)
            if incomplete:
                _logger.warning(
                    '[PAYROLL] รอบ %s: สลิป %s ใบยังไม่มีรายละเอียด '
                    'จึงยืนยันไม่ได้ (%s)', rec.display_name, len(incomplete),
                    ', '.join(incomplete.mapped('employee_code')))
            rec._sync_pnd1_safe()
        return True

    def _sync_pnd1_safe(self):
        """สร้างบรรทัด ภ.ง.ด.1 จากสลิปในรอบนี้

        ครอบด้วย savepoint เพราะ ภ.ง.ด.1 เป็นรายงานปลายทาง ถ้าสร้างไม่สำเร็จ
        ต้องไม่ทำให้การอนุมัติรอบเงินเดือนล้มไปด้วย — ยอดเงินเดือนสำคัญกว่า
        และรันซ้ำได้เสมอเพราะลบของเดิมก่อนสร้างใหม่
        """
        for rec in self:
            try:
                with rec.env.cr.savepoint():
                    rec.env['pnd1.line'].sync_from_period(rec)
            except Exception:
                _logger.exception('[PND1] สร้างข้อมูลของรอบ %s ไม่สำเร็จ',
                                  rec.display_name)
        return True

    def action_mark_paid(self):
        for rec in self:
            if rec.state != 'approved':
                raise UserError('ต้องอนุมัติรอบก่อนจึงจะบันทึกว่าจ่ายแล้วได้')
            rec.state = 'paid'
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    def action_reset_draft(self):
        """ดึงรอบกลับเป็นร่าง — ต้องดึงสลิปกลับด้วย ไม่งั้นแก้ยอดไม่ได้

        สลิปที่ยืนยันแล้วจะไม่ยอมให้คำนวณใหม่ ถ้าดึงแต่รอบกลับ
        จะได้รอบร่างที่มีสลิปยืนยันค้างอยู่ แก้อะไรไม่ได้เลย
        """
        for rec in self:
            rec.salary_ids.filtered(lambda s: s.state == 'done').action_reset_draft()
            rec.state = 'draft'
        return True

    def action_view_salaries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'รายการเงินเดือน — %s' % self.display_name,
            'res_model': 'payroll.salary',
            'view_mode': 'list,form',
            'domain': [('period_id', '=', self.id)],
            'context': {'default_period_id': self.id},
        }

    @api.model
    def _get_or_create(self, month, year, company=None):
        """หา/สร้างรอบของเดือนนั้น — ใช้ตอนสร้างสลิปเดี่ยวโดยไม่ผ่านหน้ารอบ"""
        company = company or self.env.company
        period = self.sudo().search([
            ('month', '=', int(month)), ('year', '=', int(year)),
            ('company_id', '=', company.id),
        ], limit=1)
        if period:
            return period
        start_day = company.hrms_cutoff_start_day or 25
        return self.sudo().create({
            'month': int(month), 'year': int(year), 'company_id': company.id,
            'cutoff_start_day': start_day,
            'cutoff_end_day': max(1, start_day - 1),
        })
