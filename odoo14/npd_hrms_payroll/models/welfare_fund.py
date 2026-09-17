# -*- coding: utf-8 -*-
"""หักเงินสงเคราะห์ลูกจ้าง — ตั้งอัตราครั้งเดียว ระบบหักให้เองทุกรอบเงินเดือน

พอร์ตจาก Odoo 14 (employee_salary/models/welfare_fund.py) ต่างกันตรงที่
Odoo 18 เป็นฐานข้อมูลเดียวหลายบริษัท รายการจึงผูกกับบริษัท และตอนทำเงินเดือน
ใช้เฉพาะรายการของบริษัทที่พนักงานสังกัด

ทำไมแยกเป็นเมนู: อัตรากับรายชื่อคนที่ถูกหักเปลี่ยนตามมติบริษัทเป็นครั้งคราว
ถ้าฝังในโค้ดหรือให้กรอกรายคนทุกเดือนจะตกหล่น และย้อนตรวจไม่ได้ว่าใครเริ่มหักเมื่อไหร่

ฐานคำนวณ = รายได้รวมของรอบนั้น ค่าเริ่มต้นไม่รวมค่าคอมมิชชั่น (คอมสาขา + คอม Sale)
ติ๊ก include_commission ในรายการเมื่อต้องการให้นำค่าคอมมาคิดด้วย
"""
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

RATE_SELECTION = [
    ('0.25', '0.25%'),
    ('0.50', '0.50%'),
]

MONTH_SELECTION = [
    ('1', 'มกราคม'), ('2', 'กุมภาพันธ์'), ('3', 'มีนาคม'), ('4', 'เมษายน'),
    ('5', 'พฤษภาคม'), ('6', 'มิถุนายน'), ('7', 'กรกฎาคม'), ('8', 'สิงหาคม'),
    ('9', 'กันยายน'), ('10', 'ตุลาคม'), ('11', 'พฤศจิกายน'), ('12', 'ธันวาคม'),
]


class WelfareFundConfig(models.Model):
    _name = 'welfare.fund.config'
    _description = 'หักเงินสงเคราะห์ลูกจ้าง'
    _inherit = ['mail.thread']
    _order = 'start_year desc, start_month desc, id desc'

    name = fields.Char(string='ชื่อรายการ', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True,
        default=lambda self: self.env.company, tracking=True)

    rate = fields.Selection(
        RATE_SELECTION, string='อัตราหัก', default='0.25', required=True, tracking=True,
        help='อัตราที่หักจากรายได้รวมของรอบ ตามเกณฑ์ฐานคำนวณที่เลือกด้านล่าง')
    include_commission = fields.Boolean(
        string='รวมค่าคอมมิชชั่นในฐานคำนวณ', default=False, tracking=True,
        help='ค่าเริ่มต้นคือไม่รวม — ฐานคิดจะเป็นรายได้รวมของรอบ หักค่าคอมมิชชั่น '
             '(คอมสาขา + คอม Sale) ออกก่อน\n'
             'ติ๊กช่องนี้เมื่อมติบริษัทให้เอาค่าคอมมิชชั่นมาคิดด้วย')
    apply_scope = fields.Selection([
        ('all', 'หักทุกคน'),
        ('selected', 'หักเฉพาะคนที่เลือก'),
    ], string='ขอบเขตการหัก', default='all', required=True, tracking=True,
        help='หักทุกคน = พนักงานของบริษัทนี้ที่ทำเงินเดือนรอบนั้นถูกหักทั้งหมด '
             'ยกเว้นคนที่ติ๊ก "ไม่หักคนนี้"\n'
             'หักเฉพาะคนที่เลือก = หักเฉพาะรายชื่อในตารางด้านล่าง')

    start_month = fields.Selection(
        MONTH_SELECTION, string='เริ่มหักเดือน', required=True, tracking=True,
        default=lambda self: str(fields.Date.context_today(self).month))
    start_year = fields.Char(
        string='ปี (ค.ศ.)', required=True, tracking=True,
        default=lambda self: str(fields.Date.context_today(self).year))

    cutoff_start_day = fields.Integer(
        string='วันเริ่มรอบ', required=True,
        default=lambda self: self.env.company.hrms_cutoff_start_day or 25,
        help='วันที่เริ่มรอบเงินเดือน (ของเดือนก่อน) ตั้งต้นตามรอบตัดของบริษัท ปกติ 25')
    cutoff_end_day = fields.Integer(
        string='วันตัดรอบ', required=True,
        default=lambda self: ((self.env.company.hrms_cutoff_start_day or 25) - 1) or 31,
        help='วันที่ตัดรอบเงินเดือน (ของเดือนนี้) ปกติ 24')
    cutoff_summary = fields.Char(string='รอบทำเงินเดือน', compute='_compute_cutoff_summary')

    line_ids = fields.One2many('welfare.fund.line', 'config_id', string='รายชื่อพนักงาน')
    employee_count = fields.Integer(
        string='จำนวนพนักงานที่ถูกหัก', compute='_compute_employee_count')

    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('confirmed', 'ยืนยันแล้ว'),
    ], string='สถานะ', default='draft', required=True, tracking=True,
        help='ระบบจะหักเงินให้เฉพาะรายการที่ยืนยันแล้วเท่านั้น')
    note = fields.Text(string='หมายเหตุ')

    # ------------------------------------------------------------------
    # Compute / constraint
    # ------------------------------------------------------------------
    @api.depends('rate', 'apply_scope', 'start_month', 'start_year', 'include_commission')
    def _compute_name(self):
        months = dict(MONTH_SELECTION)
        scopes = {'all': 'ทุกคน', 'selected': 'เฉพาะคนที่เลือก'}
        for rec in self:
            rec.name = 'หักเงินสงเคราะห์ %s%% เริ่ม %s %s (%s, %s)' % (
                rec.rate or '-',
                months.get(rec.start_month, '-'),
                rec.start_year or '-',
                scopes.get(rec.apply_scope, '-'),
                'รวมค่าคอม' if rec.include_commission else 'ไม่รวมค่าคอม',
            )

    @api.depends('cutoff_start_day', 'cutoff_end_day')
    def _compute_cutoff_summary(self):
        for rec in self:
            rec.cutoff_summary = 'วันที่ %s ถึง %s' % (rec.cutoff_start_day, rec.cutoff_end_day)

    @api.depends('line_ids', 'line_ids.skip_deduction')
    def _compute_employee_count(self):
        for rec in self:
            rec.employee_count = len(rec.line_ids.filtered(lambda l: not l.skip_deduction))

    @api.constrains('cutoff_start_day', 'cutoff_end_day')
    def _check_cutoff_days(self):
        for rec in self:
            if not (1 <= rec.cutoff_start_day <= 31) or not (1 <= rec.cutoff_end_day <= 31):
                raise ValidationError('วันเริ่มรอบ/วันตัดรอบ ต้องอยู่ระหว่าง 1 ถึง 31')

    @api.constrains('start_year')
    def _check_start_year(self):
        for rec in self:
            try:
                year = int(rec.start_year)
            except (TypeError, ValueError):
                raise ValidationError('กรุณากรอกปีเป็น ค.ศ. 4 หลัก เช่น 2026')
            if year < 2000 or year > 2999:
                raise ValidationError('กรุณากรอกปีเป็น ค.ศ. 4 หลัก เช่น 2026')

    @api.constrains('state', 'start_month', 'start_year', 'company_id')
    def _check_unique_confirmed_start(self):
        """กันรายการที่ยืนยันแล้วซ้ำเดือนเดียวกันของบริษัทเดียวกัน ไม่งั้นเดาไม่ออกว่าใช้อัตราไหน"""
        for rec in self.filtered(lambda r: r.state == 'confirmed'):
            if self.sudo().search_count([
                ('id', '!=', rec.id),
                ('state', '=', 'confirmed'),
                ('company_id', '=', rec.company_id.id),
                ('start_month', '=', rec.start_month),
                ('start_year', '=', rec.start_year),
            ]):
                raise ValidationError(
                    'มีรายการที่ยืนยันแล้วของเดือน %s/%s ในบริษัทนี้อยู่ก่อนแล้ว '
                    'แก้ไขรายการเดิม หรือเปลี่ยนเดือนที่เริ่มหัก'
                    % (rec.start_month, rec.start_year))

    # ------------------------------------------------------------------
    # ปุ่ม
    # ------------------------------------------------------------------
    def action_refresh_employees(self):
        """ดึงพนักงานสถานะใช้งานอยู่ของบริษัทนี้เข้ามาในตาราง (รายชื่อเดิมไม่ถูกแตะ)"""
        Employee = self.env['employee.salary'].sudo()
        for rec in self:
            existing = rec.line_ids.mapped('employee_id').ids
            employees = Employee.search([
                ('company_id', '=', rec.company_id.id),
                ('status', '=', 'active'),
                ('id', 'not in', existing),
            ], order='employee_code')
            rec.line_ids = [(0, 0, {'employee_id': emp.id}) for emp in employees]
            _logger.info('[WELFARE] %s: เพิ่มพนักงาน %d คน', rec.name, len(employees))
        return True

    def action_confirm(self):
        for rec in self:
            if (rec.apply_scope == 'selected'
                    and not rec.line_ids.filtered(lambda l: not l.skip_deduction)):
                raise ValidationError('เลือกหักเฉพาะคนที่เลือก แต่ยังไม่มีรายชื่อพนักงาน')
            rec.state = 'confirmed'
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    # ------------------------------------------------------------------
    # ใช้ตอนทำเงินเดือน
    # ------------------------------------------------------------------
    @api.model
    def get_policy_for(self, employee, month, year):
        """นโยบายหักเงินสงเคราะห์ของพนักงานคนนี้ในรอบเดือน/ปีที่ระบุ

        คืน {'rate': อัตรา %, 'include_commission': เอาค่าคอมมาคิดด้วยไหม}
        ไม่เข้าเงื่อนไข → rate = 0.0

        ใช้รายการที่ยืนยันแล้วของบริษัทพนักงาน ซึ่งเริ่มหักไม่เกินรอบนี้ และเริ่มช้าที่สุด
        (ตั้งรายการใหม่ทับของเก่าได้โดยไม่ต้องลบของเดิม จึงย้อนดูได้ว่ารอบไหนใช้เกณฑ์ไหน)
        """
        none_policy = {'rate': 0.0, 'include_commission': False}
        if not employee:
            return none_policy
        try:
            key = (int(year), int(month))
        except (TypeError, ValueError):
            return none_policy

        company = employee.company_id or self.env.company
        eligible = []
        for cfg in self.sudo().search([
                ('state', '=', 'confirmed'), ('company_id', '=', company.id)]):
            try:
                cfg_key = (int(cfg.start_year), int(cfg.start_month))
            except (TypeError, ValueError):
                continue
            if cfg_key <= key:
                eligible.append((cfg_key, cfg.id, cfg))
        if not eligible:
            return none_policy

        cfg = max(eligible, key=lambda item: (item[0], item[1]))[2]
        line = cfg.line_ids.filtered(lambda l: l.employee_id.id == employee.id)[:1]
        if line and line.skip_deduction:
            return none_policy
        if cfg.apply_scope == 'selected' and not line:
            return none_policy
        rate = (line.rate if line else False) or cfg.rate
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            return none_policy
        return {'rate': rate, 'include_commission': bool(cfg.include_commission)}

    @api.model
    def get_rate_for(self, employee, month, year):
        """อัตราหักอย่างเดียว"""
        return self.get_policy_for(employee, month, year)['rate']


class WelfareFundLine(models.Model):
    _name = 'welfare.fund.line'
    _description = 'รายชื่อพนักงานที่หักเงินสงเคราะห์'
    _rec_name = 'employee_id'
    _order = 'employee_code'

    config_id = fields.Many2one(
        'welfare.fund.config', string='รายการ', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        related='config_id.company_id', string='บริษัท', store=True, readonly=True)
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True, ondelete='cascade')
    employee_code = fields.Char(
        related='employee_id.employee_code', string='รหัสพนักงาน', store=True, readonly=True)
    firstname = fields.Char(
        related='employee_id.firstname', string='ชื่อ', readonly=True)
    lastname = fields.Char(
        related='employee_id.lastname', string='นามสกุล', readonly=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', string='สาขา', readonly=True)
    department_id = fields.Many2one(
        related='employee_id.department_id', string='แผนก', readonly=True)
    employee_status = fields.Selection(
        related='employee_id.status', string='สถานะพนักงาน', readonly=True)

    rate = fields.Selection(
        RATE_SELECTION, string='อัตราเฉพาะราย',
        help='เว้นว่าง = ใช้อัตราของรายการหลัก')
    skip_deduction = fields.Boolean(
        string='ไม่หักคนนี้',
        help='ติ๊กเมื่อไม่ต้องการหักพนักงานคนนี้ โดยไม่ต้องลบชื่อออกจากรายการ')
    note = fields.Char(string='หมายเหตุ')

    _sql_constraints = [
        ('employee_config_uniq', 'unique(config_id, employee_id)',
         'พนักงานคนนี้มีอยู่ในรายการแล้ว'),
    ]
