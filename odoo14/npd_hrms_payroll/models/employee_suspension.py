# -*- coding: utf-8 -*-
"""คำสั่งพักงาน — เก็บที่ตัวพนักงาน ไม่ใช่ที่ใบเงินเดือน

เดิมกรอกช่วงพักงานไว้ที่ใบเงินเดือนโดยตรง ซึ่งมีปัญหาสามข้อ
  1. ถ้า HR ลบใบแล้วสร้างใหม่ ข้อมูลพักงานหายเงียบโดยไม่มีใครรู้
  2. พักงานที่คร่อมสองรอบ (เช่น 20 ก.ย. ถึง 5 ต.ค.) ต้องกรอกสองใบและแบ่งวันเอง
  3. แอปต้องมีที่เดียวให้ถามว่า "วันนี้คนนี้ถูกพักงานอยู่ไหม" ซึ่งใบเงินเดือน
     ตอบไม่ได้ เพราะรอบของเดือนนั้นอาจยังไม่ถูกสร้าง

ย้ายมาเก็บเป็นรายการของพนักงาน บันทึกแค่ช่วงวันที่จริง ไม่ต้องระบุรอบเงินเดือน
ตอนคำนวณเงินเดือน ระบบหาเองว่าช่วงไหนทับกับรอบนั้น แล้วคิดให้ทีละวัน
ถ้าวันตัดรอบเปลี่ยนภายหลัง ข้อมูลก็ยังถูกต้องเพราะยึดวันที่จริงเป็นหลัก
"""
import datetime
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

DEFAULT_SUSPENSION_DEDUCT_PERCENT = 50.0


class EmployeeSuspension(models.Model):
    _name = 'employee.suspension'
    _description = 'คำสั่งพักงาน'
    _order = 'date_start desc, id desc'
    _rec_name = 'display_name'

    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True,
        ondelete='cascade', index=True)
    employee_code = fields.Char(related='employee_id.employee_code',
                                string='รหัสพนักงาน', store=True, readonly=True)
    date_start = fields.Date(string='วันที่เริ่มพักงาน', required=True)
    date_end = fields.Date(string='วันที่สิ้นสุดพักงาน', required=True,
                           help='นับรวมวันนี้ด้วย')
    deduct_percent = fields.Float(
        string='หักกี่ % ต่อวัน', default=DEFAULT_SUSPENSION_DEDUCT_PERCENT,
        required=True,
        help='ค่าเริ่มต้น 50 คือจ่ายครึ่งหนึ่งของค่าจ้างรายวัน')
    reason = fields.Char(string='เหตุผลที่พักงาน', required=True,
                         help='ข้อความนี้จะถูกแสดงในแอปตอนพนักงานกดเข้าหน้าลงเวลา')
    note = fields.Text(string='หมายเหตุเพิ่มเติม')
    active = fields.Boolean(string='ใช้งาน', default=True,
                            help='ยกเลิกคำสั่งพักงานได้โดยไม่ต้องลบประวัติทิ้ง')

    day_count = fields.Integer(string='จำนวนวัน', compute='_compute_day_count',
                               store=True)
    period_hint = fields.Char(string='ตกรอบเงินเดือน',
                              compute='_compute_period_hint',
                              help='ช่วงนี้ไปตกอยู่ในรอบเงินเดือนไหนบ้าง '
                                   'คำนวณให้ดูเฉย ๆ ระบบไม่ได้ยึดค่านี้ '
                                   'ตอนคิดเงินจะเทียบวันที่จริงเสมอ')

    @api.depends('date_start', 'date_end')
    def _compute_day_count(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end >= rec.date_start:
                rec.day_count = (rec.date_end - rec.date_start).days + 1
            else:
                rec.day_count = 0

    @api.depends('date_start', 'date_end')
    def _compute_period_hint(self):
        """บอกว่าช่วงนี้ตกรอบไหนบ้าง (รอบตัด 25 ถึง 24 ของเดือนถัดไป)"""
        for rec in self:
            if not (rec.date_start and rec.date_end):
                rec.period_hint = ''
                continue
            periods, cur = [], rec.date_start
            while cur <= rec.date_end:
                # วันที่ 25 เป็นต้นไป นับเข้ารอบของเดือนถัดไป
                month = cur.month + 1 if cur.day >= 25 else cur.month
                year = cur.year
                if month > 12:
                    month, year = 1, year + 1
                label = '%02d/%d' % (month, year)
                if label not in periods:
                    periods.append(label)
                cur += datetime.timedelta(days=1)
            rec.period_hint = ', '.join(periods)

    @api.depends('employee_id', 'date_start', 'date_end')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s: %s ถึง %s' % (
                rec.employee_id.display_name or '-',
                rec.date_start or '-', rec.date_end or '-')

    # ------------------------------------------------------------------
    @api.constrains('date_start', 'date_end')
    def _check_range(self):
        for rec in self:
            if rec.date_end < rec.date_start:
                raise ValidationError(_(
                    'วันที่สิ้นสุดพักงาน (%s) ต้องไม่ก่อนวันที่เริ่มพักงาน (%s)'
                ) % (rec.date_end, rec.date_start))

    @api.constrains('deduct_percent')
    def _check_percent(self):
        for rec in self:
            if not (0.0 <= rec.deduct_percent <= 100.0):
                raise ValidationError(_(
                    'หักกี่ % ต่อวัน ต้องอยู่ระหว่าง 0 ถึง 100 (ใส่มา %s)'
                ) % rec.deduct_percent)

    @api.constrains('employee_id', 'date_start', 'date_end', 'active')
    def _check_overlap(self):
        """คำสั่งพักงานของคนเดียวกันต้องไม่ทับช่วงกัน

        ถ้าทับกันจะไม่รู้ว่าวันนั้นต้องใช้ % ของคำสั่งไหน และอาจหักซ้อนกันเอง
        """
        for rec in self:
            if not rec.active:
                continue
            other = self.search([
                ('id', '!=', rec.id),
                ('employee_id', '=', rec.employee_id.id),
                ('active', '=', True),
                ('date_start', '<=', rec.date_end),
                ('date_end', '>=', rec.date_start),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    'ช่วงพักงานนี้ทับกับคำสั่งเดิมของพนักงานคนเดียวกัน '
                    '(%s ถึง %s)\nกรุณาแก้ช่วงให้ไม่ทับกัน'
                ) % (other.date_start, other.date_end))

    # ------------------------------------------------------------------
    @api.model
    def suspension_on(self, employee, day):
        """คำสั่งพักงานที่ครอบวันนี้ของพนักงานคนนี้ (ไม่มี = recordset ว่าง)

        ใช้ได้ทั้งตอนคิดเงินเดือนและตอนแอปถามว่าวันนี้ถูกพักงานอยู่ไหม
        """
        if not (employee and day):
            return self.browse()
        return self.sudo().search([
            ('employee_id', '=', employee.id),
            ('active', '=', True),
            ('date_start', '<=', day),
            ('date_end', '>=', day),
        ], limit=1)

    @api.model
    def suspensions_in_range(self, employee, date_from, date_to):
        """คำสั่งพักงานทั้งหมดที่ทับช่วงที่กำหนด"""
        if not (employee and date_from and date_to):
            return self.browse()
        return self.sudo().search([
            ('employee_id', '=', employee.id),
            ('active', '=', True),
            ('date_start', '<=', date_to),
            ('date_end', '>=', date_from),
        ])


class EmployeeSalarySuspension(models.Model):
    _inherit = 'employee.salary'

    suspension_ids = fields.One2many(
        'employee.suspension', 'employee_id', string='ประวัติการพักงาน')
    suspension_count = fields.Integer(string='จำนวนคำสั่งพักงาน',
                                      compute='_compute_suspension_count')
    is_suspended_today = fields.Boolean(
        string='วันนี้ถูกพักงานอยู่', compute='_compute_is_suspended_today',
        help='ใช้ดูเร็ว ๆ ว่าตอนนี้ยังอยู่ในช่วงพักงานไหม')

    @api.depends('suspension_ids')
    def _compute_suspension_count(self):
        for rec in self:
            rec.suspension_count = len(rec.suspension_ids.filtered('active'))

    def _compute_is_suspended_today(self):
        today = fields.Date.context_today(self)
        Suspension = self.env['employee.suspension']
        for rec in self:
            rec.is_suspended_today = bool(Suspension.suspension_on(rec, today))
