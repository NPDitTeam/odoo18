# -*- coding: utf-8 -*-
"""สลิปเงินเดือน (payroll.salary)

พอร์ตจาก Odoo 14 — โครงสร้างฟิลด์และชื่อบรรทัดในสลิปคงเดิมทั้งหมด
เพื่อให้แอปและรายงานที่อ่านคีย์เดิมยังใช้ได้

สิ่งที่เปลี่ยน
--------------
1. ตัดการเรียก PHP ออกหมด — สาย/ขาด/ลา/OT คำนวณเองใน ``payroll.attendance.engine``
   (เดิมยิง calculate_lateness.php + get_ot_data.php)
2. ค่าเที่ยว/เบี้ยเลี้ยงคนขับอ่านจาก ``vehicle.booking`` ผ่าน ORM (เดิม login
   ข้ามเซิร์ฟเวอร์ไป npd-solution.com แล้วดึง JSON) — DB เดียวกันแล้ว
3. อัตราประกันสังคม/เพดาน/วันตัดรอบ/อัตรา OT อ่านจาก ``res.company``
4. ตัด ``EXECUTIVE_TAX_CONFIG`` ที่ hardcode รหัสพนักงานผู้บริหารไว้ในโค้ด
   → ใช้ธง ``payroll_exempt_*`` บนบัตรพนักงานแทน (ตั้งค่าได้ ไม่ต้องแก้โค้ด)
"""
import calendar
import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .payroll_attendance_engine import round_half_up

_logger = logging.getLogger(__name__)


class PayrollSalary(models.Model):
    _name = 'payroll.salary'
    _description = 'สลิปเงินเดือน'
    _inherit = ['mail.thread']
    _order = 'year desc, month desc, employee_code'
    _rec_name = 'display_name'

    _sql_constraints = [
        ('employee_period_uniq', 'unique(employee_id, month, year, company_id)',
         'พนักงานคนนี้มีรายการเงินเดือนของเดือน/ปีนี้อยู่แล้ว'),
    ]

    # ==================================================================
    # ข้อมูลหลัก
    # ==================================================================
    period_id = fields.Many2one(
        'payroll.period', string='รอบเงินเดือน', ondelete='set null', index=True)
    employee_id = fields.Many2one(
        'employee.salary', string='ชื่อพนักงาน', required=True,
        ondelete='restrict', index=True)
    employee_code = fields.Char(
        related='employee_id.employee_code', store=True, readonly=True, index=True)
    firstname = fields.Char(related='employee_id.firstname', store=True, readonly=True)
    lastname = fields.Char(related='employee_id.lastname', store=True, readonly=True)
    branch_id = fields.Many2one(
        'res.branch', related='employee_id.branch_id', store=True, readonly=True)
    department_id = fields.Many2one(
        'hr.department.custom', related='employee_id.department_id',
        store=True, readonly=True)
    position_id = fields.Many2one(
        'hr.position.custom', related='employee_id.position_id',
        store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True,
        default=lambda self: self.env.company)
    transfer_type = fields.Selection(
        related='employee_id.transfer_type', store=True, readonly=True)

    month = fields.Integer(
        string='เดือน', required=True,
        default=lambda self: fields.Date.context_today(self).month)
    year = fields.Char(
        string='ปี', required=True,
        default=lambda self: str(fields.Date.context_today(self).year))
    cutoff_day = fields.Integer(string='วันตัดรอบ', required=True, default=24)
    payment_date = fields.Date(
        string='วันที่จ่ายเงิน', default=lambda self: self._default_payment_date())
    active = fields.Boolean(default=True, index=True)
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('done', 'ยืนยันแล้ว'),
    ], string='สถานะ', default='draft', required=True, tracking=True)

    base_salary = fields.Float(
        string='ฐานเงินเดือน', related='employee_id.salary', store=True, readonly=True)

    # ==================================================================
    # รายได้
    # ==================================================================
    income_cost_of_living = fields.Float(
        string='เงินค่าครองชีพ', related='employee_id.cost_of_living',
        store=True, readonly=True)
    income_position_allowance = fields.Float(
        string='เงินประจำตำแหน่ง', related='employee_id.position_allowance',
        store=True, readonly=True)
    income_experience_allowance = fields.Float(
        string='เงินค่าประสบการณ์', related='employee_id.experience_allowance',
        store=True, readonly=True)
    income_professional_allowance = fields.Float(
        string='เงินค่าวิชาชีพ', related='employee_id.professional_allowance',
        store=True, readonly=True)

    income_allowance = fields.Float(string='เบี้ยเลี้ยง นอกสถานที่', default=0.0)
    income_food = fields.Float(string='ค่าอาหาร', default=0.0)
    income_transport = fields.Float(
        string='ค่าเดินทาง', compute='_compute_income_transport', store=True, readonly=False)
    income_transport_trip = fields.Float(string='ค่าเที่ยวขนส่ง', default=0.0)
    income_transport_allowance = fields.Float(string='ค่าเบี้ยเลี้ยงขนส่ง', default=0.0)
    income_fuel = fields.Float(string='อินเซนทีฟ', default=0.0)
    income_commission = fields.Float(string='ค่าคอมมิชชั่นสาขา', default=0.0)
    income_commission_sale = fields.Float(string='ค่าคอมมิชชั่น Sale', default=0.0)

    income_other_manual = fields.Float(string='รายได้อื่นๆ (ใส่เพิ่ม)', default=0.0)
    income_manual_request = fields.Float(
        string='รายได้อื่นๆ จากคำขอเพิ่มเวลา', default=0.0, readonly=True,
        help='ยอดของประเภทคำขอเพิ่มเวลาที่ตั้งช่องปลายทางเป็น "รายได้อื่นๆ" '
             'เช่น ค่ารักษาพยาบาล — เก็บแยกเพราะช่องรายได้อื่นๆ เป็นช่องรวมที่คำนวณเอง')
    income_bonus = fields.Float(string='โบนัส', default=0.0)
    bonus_active = fields.Boolean(
        string='ใช้โบนัสเดือนนี้', default=False,
        help='ติ๊กเพื่อให้โบนัสนับรวมเดือนนี้ — เดือนถัดไปจะไม่ติ๊กให้อัตโนมัติ')
    income_missed_payment = fields.Float(
        string='เงินตกหล่นจากรอบก่อน', default=0.0)
    other_income_total = fields.Float(
        string='เงินได้อื่นๆ (จากเมนู)', compute='_compute_other_income',
        store=True, readonly=True)
    actor_content_total = fields.Float(
        string='ค่าตัวนักแสดง ถ่าย content', compute='_compute_other_income',
        store=True, readonly=True)
    income_deposit_refund_total = fields.Float(
        string='คืนเงินประกันการทำงาน', compute='_compute_deposit_amounts',
        store=True, readonly=True)
    income_other = fields.Float(
        string='รายได้อื่นๆ (รวมทั้งหมด)', compute='_compute_income_other',
        store=True, readonly=True,
        help='รวม: ใส่เพิ่ม + ค่าตัวนักแสดง + โบนัส + เงินตกหล่น + เมนูเงินได้อื่นๆ + คืนเงินประกัน')

    # OT
    ot_line_ids = fields.One2many('payroll.ot.line', 'payroll_id', string='รายการ OT')
    ot_total_weekday = fields.Float(string='ค่าล่วงเวลา/โอที', readonly=True)
    ot_total_holiday = fields.Float(string='ค่าล่วงเวลา/วันหยุดนักขัตฤกษ์', readonly=True)
    ot_total_sunday = fields.Float(string='ค่าล่วงเวลา', readonly=True)
    ot_total = fields.Float(
        string='ค่าล่วงเวลารวม', compute='_compute_ot_total', store=True)
    ot_calculation_method = fields.Selection([
        ('round_down', 'ปัดเศษเป็นชั่วโมงเต็ม'),
        ('actual', 'คำนวณตามจริง'),
    ], string='วิธีคำนวณชั่วโมง OT', default='round_down', required=True)
    override_ot = fields.Boolean(string='ปรับแก้ OT ด้วยมือ', default=False)

    # ==================================================================
    # รายการหัก
    # ==================================================================
    expense_provident = fields.Float(string='กองทุนสำรองเลี้ยงชีพ', default=0.0)
    expense_advance = fields.Float(string='เบิกเงินล่วงหน้า', default=0.0)
    expense_loan = fields.Float(string='เงินกู้', default=0.0)
    expense_ksl = fields.Float(string='กยศ.', default=0.0)
    expense_other_manual = fields.Float(string='หักอื่นๆ (ใส่เพิ่ม)', default=0.0)
    expense_deposit_regular_total = fields.Float(
        string='หักเงินประกันรายเดือน', compute='_compute_deposit_amounts',
        store=True, readonly=True)
    expense_deposit_extra_total = fields.Float(
        string='หัก Work Permit / อื่นๆ', compute='_compute_deposit_amounts',
        store=True, readonly=True)
    expense_other = fields.Float(
        string='หักอื่นๆ (รวมทั้งหมด)', compute='_compute_expense_other',
        store=True, readonly=True)

    deduction_late = fields.Float(string='หักสาย', readonly=True)
    deduction_leave = fields.Float(string='หักลากิจ', readonly=True)
    deduction_absent = fields.Float(string='หักขาดงาน', readonly=True)
    missed_days_deduction = fields.Float(string='ยอดหักขาดงาน', readonly=True)
    late_checkin_deduction = fields.Float(string='ยอดหักสาย', readonly=True)
    early_checkout_deduction = fields.Float(string='ยอดหักออกก่อนเวลา', readonly=True)
    lateness_deduction = fields.Float(string='ยอดหักรวม (สาย/ลา/ขาด)', readonly=True)
    leave_deduction_total = fields.Float(string='ยอดหักจากการลา', readonly=True)

    late_checkin_minutes = fields.Float(string='รวมเวลาสาย (นาที)', readonly=True)
    early_checkout_minutes = fields.Float(string='รวมเวลาออกก่อน (นาที)', readonly=True)
    lateness_minutes = fields.Float(string='รวมเวลาสาย+ออกก่อน (นาที)', readonly=True)
    missed_days = fields.Integer(string='จำนวนวันขาดงาน', readonly=True)
    working_days = fields.Integer(string='จำนวนวันทำงานในรอบ', readonly=True)
    present_days = fields.Integer(string='จำนวนวันมาทำงาน', readonly=True)
    missed_days_detail = fields.Text(string='รายละเอียดวันขาดงาน', readonly=True)
    deduction_line_ids = fields.One2many(
        'payroll.deduction.line', 'payroll_id',
        string='แจกแจงการหักรายวัน', readonly=True)

    lateness_grace_period = fields.Integer(
        string='ผ่อนผันเวลาสาย (นาที)',
        default=lambda self: self.env.company.hrms_ot_grace_period or 15)

    # ==================================================================
    # ประกันสังคม / ภาษี
    # ==================================================================
    policy_id = fields.Many2one(
        'payroll.policy', string='นโยบายการคำนวณ', readonly=True,
        help='สูตรที่ใช้คำนวณสลิปใบนี้ — เก็บไว้เพื่อให้ตรวจย้อนหลังได้ว่า '
             'ตอนนั้นใช้กติกาแบบไหน')
    sso_total = fields.Float(string='ประกันสังคม/เดือน', readonly=True)
    sso_base_used = fields.Float(
        string='ฐานที่ใช้คิดประกันสังคม', readonly=True)
    sso_annual_used = fields.Float(
        string='ประกันสังคม/ปี (ใช้ลดหย่อน)', compute='_compute_sso_annual',
        store=True, readonly=True)
    manual_override_sso = fields.Boolean(string='ปรับ ปกส. ด้วยมือ', default=False)
    manual_sso_amount = fields.Float(string='ประกันสังคม (กรอกเอง)', default=0.0)

    tax_monthly = fields.Float(string='ภาษีหัก ณ ที่จ่าย', readonly=True)
    tax_annual = fields.Float(string='ประมาณการภาษี (ต่อปี)', readonly=True)
    manual_override_tax = fields.Boolean(string='ปรับภาษีด้วยมือ', default=False)
    manual_tax_amount = fields.Float(string='ภาษี (กรอกเอง/เดือน)', default=0.0)
    tax_bracket_ids = fields.One2many(
        'payroll.tax.bracket', 'payroll_id', string='ขั้นบันไดอัตราภาษี',
        help='สำเนาขั้นภาษีที่ใช้ตอนคำนวณสลิปใบนี้ — แก้นโยบายภายหลังจะไม่กระทบสลิปเก่า')

    # เพดาน/อัตราตามกฎหมายอยู่ที่ payroll.policy — ตรงนี้เก็บเฉพาะค่าที่ต่างรายคน
    child_deduction = fields.Float(string='ค่าลดหย่อนบุตร', default=0.0)
    provident_fund_rate = fields.Float(string='อัตรากองทุนสำรองเลี้ยงชีพ (%)', default=0.0)

    # ค่าลดหย่อนเพิ่มเติม (กรอกยอดต่อปี — ต่างรายคน)
    ded_spouse = fields.Float(string='คู่สมรส (ไม่มีเงินได้)', default=0.0)
    ded_parents = fields.Float(string='อุปการะบิดามารดา', default=0.0)
    ded_disabled = fields.Float(string='อุปการะผู้พิการ/ทุพพลภาพ', default=0.0)
    ded_life_insurance = fields.Float(string='เบี้ยประกันชีวิต', default=0.0)
    ded_health_insurance = fields.Float(string='เบี้ยประกันสุขภาพตนเอง', default=0.0)
    ded_parents_health_insurance = fields.Float(
        string='เบี้ยประกันสุขภาพบิดามารดา', default=0.0)
    ded_pension_insurance = fields.Float(string='เบี้ยประกันชีวิตแบบบำนาญ', default=0.0)
    ded_rmf = fields.Float(string='กองทุน RMF', default=0.0)
    ded_ssf = fields.Float(string='กองทุน SSF', default=0.0)
    ded_thaiesg = fields.Float(string='กองทุน ThaiESG', default=0.0)
    ded_pension_fund = fields.Float(string='กองทุนสำรองเลี้ยงชีพ (เพิ่มเติม)', default=0.0)
    ded_home_loan_interest = fields.Float(string='ดอกเบี้ยกู้ซื้อที่อยู่อาศัย', default=0.0)
    ded_donation = fields.Float(string='เงินบริจาคทั่วไป', default=0.0)
    ded_donation_education = fields.Float(
        string='เงินบริจาคการศึกษา/กีฬา/รพ.รัฐ (2 เท่า)', default=0.0)
    ded_shopping = fields.Float(string='ช้อปดีมีคืน / Easy E-Receipt', default=0.0)

    EXTRA_DEDUCTION_FIELDS = [
        'ded_spouse', 'ded_parents', 'ded_disabled',
        'ded_life_insurance', 'ded_health_insurance',
        'ded_parents_health_insurance', 'ded_pension_insurance',
        'ded_rmf', 'ded_ssf', 'ded_thaiesg', 'ded_pension_fund',
        'ded_home_loan_interest', 'ded_donation', 'ded_donation_education',
        'ded_shopping',
    ]

    # ==================================================================
    # ยอดรวม
    # ==================================================================
    line_ids = fields.One2many(
        'payroll.salary.line', 'payroll_id', string='รายละเอียดเงินเดือน')
    total_gross = fields.Float(
        string='รวมรายได้', compute='_compute_totals', store=True, readonly=False)
    total_deduction = fields.Float(
        string='รวมรายการหัก', compute='_compute_totals', store=True, readonly=False)
    net_salary = fields.Float(
        string='เงินสุทธิ', compute='_compute_totals', store=True, readonly=False)
    manual_override = fields.Boolean(
        string='ปรับแก้ด้วยมือ', default=False,
        help='ติ๊กแล้วระบบจะไม่สร้างบรรทัดใหม่ทับค่าที่แก้ไว้')

    opening_accumulated_income = fields.Float(string='รายรับสะสมต้นรอบ', default=0.0)
    opening_accumulated_vat = fields.Float(string='ภาษีสะสมต้นรอบ', default=0.0)
    opening_accumulated_social_security = fields.Float(
        string='ปกส.สะสมต้นรอบ', default=0.0)
    accumulated_income = fields.Float(
        string='รายรับสะสม', compute='_compute_accumulated', store=True, readonly=True)
    accumulated_vat = fields.Float(
        string='ภาษีสะสม', compute='_compute_accumulated', store=True, readonly=True)
    accumulated_social_security = fields.Float(
        string='ประกันสังคมสะสม', compute='_compute_accumulated', store=True, readonly=True)

    # ==================================================================
    # Compute
    # ==================================================================
    @api.depends('employee_id', 'month', 'year')
    def _compute_display_name(self):
        for rec in self:
            name = rec.employee_id.full_name or rec.employee_code or ''
            rec.display_name = '%s %s/%s' % (name, rec.month, rec.year)

    @api.model
    def _default_payment_date(self):
        today = fields.Date.context_today(self)
        if today.day < 28:
            return today.replace(day=28)
        return (today.replace(day=1) + relativedelta(months=1)).replace(day=28)

    @api.depends('income_transport_trip', 'income_transport_allowance')
    def _compute_income_transport(self):
        for rec in self:
            rec.income_transport = (rec.income_transport_trip or 0.0) + \
                (rec.income_transport_allowance or 0.0)

    @api.depends('ot_total_weekday', 'ot_total_holiday', 'ot_total_sunday')
    def _compute_ot_total(self):
        for rec in self:
            rec.ot_total = ((rec.ot_total_weekday or 0.0)
                            + (rec.ot_total_holiday or 0.0)
                            + (rec.ot_total_sunday or 0.0))

    @api.depends('sso_total')
    def _compute_sso_annual(self):
        for rec in self:
            rec.sso_annual_used = (rec.sso_total or 0.0) * 12

    @api.depends('employee_id', 'month', 'year', 'cutoff_day', 'payment_date')
    def _compute_other_income(self):
        """เงินได้อื่นๆ จากเมนู + ค่าตัวนักแสดงจากคำขอเพิ่มเวลา"""
        for rec in self:
            rec.other_income_total = 0.0
            rec.actor_content_total = 0.0
            if not rec.employee_id or not rec.month or not rec.year:
                continue
            date_from, date_to = rec._cycle_window()
            if not date_from:
                continue

            OtherIncome = rec.env['other.income'].sudo()
            rec.other_income_total = OtherIncome.get_total_for_cycle(
                rec.employee_id, date_from, date_to, rec.payment_date)

            # ค่าตัวนักแสดงมีช่องแยกของตัวเองในสลิป จึงกันออกจากยอดรวมทั่วไป
            totals = rec.env['hr.manual.time.log'].sudo().get_approved_totals(
                rec.employee_id, date_from, date_to,
                exclude_codes=('actor_content',))
            rec.actor_content_total = rec._actor_content_amount(date_from, date_to)
            if not rec.manual_override:
                rec._apply_manual_request_totals(totals)

    def _apply_manual_request_totals(self, totals):
        """เขียนยอดคำขอเพิ่มเวลาที่อนุมัติแล้ว ลงช่องรายได้ตามที่ตั้งไว้ในประเภท

        เดิมโค้ดอ่านแค่ ``income_allowance`` กับ ``income_food`` ทั้งที่ประเภท
        คำขอตั้งช่องปลายทางได้อิสระ ยอดของประเภทอื่น (เช่น ค่ารักษาพยาบาล)
        จึงหายไปจากสลิปเงียบ ๆ และบริษัทที่เช่าระบบเพิ่มประเภทใหม่เองไม่ได้จริง

        ช่องที่เป็นช่องรวมแบบคำนวณ (``income_other``) เขียนตรงไม่ได้
        จึงพักไว้ที่ ``income_manual_request`` แล้วให้ช่องรวมบวกต่อ
        """
        self.ensure_one()
        Reason = self.env['hrms.manual.time.reason'].sudo()
        targets = set(filter(None, Reason.with_context(active_test=False)
                             .search([]).mapped('payroll_income_field')))
        request_other = 0.0
        for name in targets:
            field = self._fields.get(name)
            if field is None:
                _logger.warning(
                    '[PAYROLL] ประเภทคำขอเพิ่มเวลาตั้งช่องรายได้เป็น %r '
                    'แต่ไม่มีช่องนี้ในสลิป — ยอดจะไม่ถูกนำเข้า', name)
                continue
            amount = totals.get(name, 0.0)
            if field.compute or not field.store or field.related:
                request_other += amount
            else:
                self[name] = amount
        self.income_manual_request = request_other

    def _actor_content_amount(self, date_from, date_to):
        """ยอดค่าตัวนักแสดงในรอบ — แยกออกมาเพราะไปรวมใน income_other ไม่ใช่ income_other_manual"""
        self.ensure_one()
        reason = self.env.ref(
            'npd_hrms_attendance.manual_reason_actor_content', raise_if_not_found=False)
        if not reason:
            return 0.0
        logs = self.env['hr.manual.time.log'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'อนุมัติ'),
            ('reason_type_id', '=', reason.id),
            ('work_date', '>=', date_from),
            ('work_date', '<=', date_to),
        ])
        return sum(logs.mapped('amount'))

    @api.depends('income_manual_request',
                 'income_other_manual', 'actor_content_total', 'income_bonus',
                 'bonus_active', 'income_missed_payment', 'other_income_total',
                 'income_deposit_refund_total')
    def _compute_income_other(self):
        for rec in self:
            rec.income_other = (
                (rec.income_other_manual or 0.0)
                + (rec.income_manual_request or 0.0)
                + (rec.actor_content_total or 0.0)
                + ((rec.income_bonus or 0.0) if rec.bonus_active else 0.0)
                + (rec.income_missed_payment or 0.0)
                + (rec.other_income_total or 0.0)
                + (rec.income_deposit_refund_total or 0.0)
            )

    @api.depends('employee_id', 'month', 'year', 'cutoff_day')
    def _compute_deposit_amounts(self):
        """เงินประกันการทำงาน — หักรายเดือน / หัก Work Permit / คืนเมื่อลาออก"""
        for rec in self:
            rec.expense_deposit_regular_total = 0.0
            rec.expense_deposit_extra_total = 0.0
            rec.income_deposit_refund_total = 0.0
            if not rec.employee_id or 'work.security.deposit' not in rec.env:
                continue
            date_from, date_to = rec._cycle_window()
            if not date_from:
                continue
            amounts = rec.env['work.security.deposit'].sudo().get_cycle_amounts(
                rec.employee_id, date_from, date_to)
            rec.expense_deposit_regular_total = amounts.get('regular', 0.0)
            rec.expense_deposit_extra_total = amounts.get('extra', 0.0)
            rec.income_deposit_refund_total = amounts.get('refund', 0.0)

    @api.depends('expense_other_manual', 'expense_deposit_regular_total',
                 'expense_deposit_extra_total')
    def _compute_expense_other(self):
        for rec in self:
            rec.expense_other = ((rec.expense_other_manual or 0.0)
                                 + (rec.expense_deposit_regular_total or 0.0)
                                 + (rec.expense_deposit_extra_total or 0.0))

    @api.depends('line_ids.amount', 'line_ids.type')
    def _compute_totals(self):
        for rec in self:
            income = sum(line.amount for line in rec.line_ids if line.type == 'income')
            deduction = sum(
                line.amount for line in rec.line_ids if line.type == 'deduction')
            rec.total_gross = income
            rec.total_deduction = deduction
            rec.net_salary = income - deduction

    @api.depends('employee_id', 'month', 'year', 'total_gross', 'tax_monthly',
                 'sso_total', 'opening_accumulated_income',
                 'opening_accumulated_vat', 'opening_accumulated_social_security')
    def _compute_accumulated(self):
        """ยอดสะสมตั้งแต่ต้นปี = ของเดือนก่อน + ของเดือนนี้ (หรือยอดต้นรอบถ้าเป็นเดือนแรก)"""
        for rec in self:
            previous = rec._previous_record()
            if previous:
                base_income = previous.accumulated_income
                base_vat = previous.accumulated_vat
                base_sso = previous.accumulated_social_security
            else:
                base_income = rec.opening_accumulated_income
                base_vat = rec.opening_accumulated_vat
                base_sso = rec.opening_accumulated_social_security
            rec.accumulated_income = base_income + (rec.total_gross or 0.0)
            rec.accumulated_vat = base_vat + (rec.tax_monthly or 0.0)
            rec.accumulated_social_security = base_sso + (rec.sso_total or 0.0)

    def _previous_record(self):
        """สลิปเดือนก่อนหน้าของพนักงานคนเดียวกัน (ปีเดียวกันเท่านั้น — สะสมรีเซ็ตทุกปี)"""
        self.ensure_one()
        if not self.employee_id or not self.month or not self.year:
            return self.browse()
        month, year = int(self.month), int(self.year)
        if month == 1:
            return self.browse()
        return self.sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('month', '=', month - 1),
            ('year', '=', str(year)),
            ('id', '!=', self.id or 0),
        ], limit=1)

    # ==================================================================
    # ช่วงรอบ
    # ==================================================================
    def _cycle_window(self):
        """(date_from, date_to) ของรอบนี้"""
        self.ensure_one()
        try:
            month, year = int(self.month), int(self.year)
        except (TypeError, ValueError):
            return False, False
        end_day = self.cutoff_day or 24
        start_day = (self.period_id.cutoff_start_day if self.period_id else 0) \
            or (self.company_id.hrms_cutoff_start_day or 25)
        last_curr = calendar.monthrange(year, month)[1]
        date_to = date(year, month, min(end_day, last_curr))
        prev = date(year, month, 1) - relativedelta(months=1)
        last_prev = calendar.monthrange(prev.year, prev.month)[1]
        date_from = date(prev.year, prev.month, min(start_day, last_prev))
        return date_from, date_to

    def _get_policy(self):
        """นโยบายการคำนวณที่ใช้กับสลิปใบนี้ (อิงวันตัดรอบ)"""
        self.ensure_one()
        if self.policy_id:
            return self.policy_id
        _date_from, date_to = self._cycle_window()
        return self.env['payroll.policy'].sudo().get_for(
            self.company_id or self.env.company, date_to or None)

    def _prorated_salary(self, policy=None):
        """เงินเดือนที่ได้จริง — prorate ให้คนเข้า/ออกกลางรอบ

        ฐาน ÷ ตัวหารวันตามนโยบาย × จำนวนวันปฏิทินที่เป็นพนักงานจริงในรอบนี้
        ⚠️ ใช้กับบรรทัดรายได้และฐานประกันสังคมเท่านั้น — ภาษียังคิดจากฐานเต็ม
        """
        self.ensure_one()
        policy = policy or self._get_policy()
        base = self.base_salary or 0.0
        employee = self.employee_id
        if not employee.resign_date and not employee.start_date:
            return base
        date_from, date_to = self._cycle_window()
        if not date_from:
            return base
        eff_start = date_from
        if employee.start_date and employee.start_date > date_from:
            eff_start = employee.start_date
        eff_end = date_to
        if employee.resign_date and employee.resign_date < date_to:
            eff_end = employee.resign_date
        if eff_start <= date_from and eff_end >= date_to:
            return base
        days_worked = max(0, (eff_end - eff_start).days + 1)
        prorated = round(base / (policy.salary_days_divisor or 30.0) * days_worked, 2)
        _logger.info(
            '[PRORATE] emp=%s eff=[%s..%s] days=%d base=%.2f -> %.2f',
            self.employee_code, eff_start, eff_end, days_worked, base, prorated)
        return prorated

    # ==================================================================
    # ภาษี
    # ==================================================================
    def _tax_income_base(self, ot_amount=None):
        """แยกเงินได้เป็น "ประจำ" (×12) กับ "ครั้งเดียว" (บวกเฉพาะเดือนที่จ่าย)

        ใช้ base_salary เต็มเสมอ เพื่อให้ฐานภาษีสม่ำเสมอทุกเดือน
        """
        self.ensure_one()
        ot = (self.ot_total if ot_amount is None else ot_amount) or 0.0
        recurring = (
            (self.base_salary or 0.0) + ot
            + (self.income_cost_of_living or 0.0)
            + (self.income_position_allowance or 0.0)
            + (self.income_experience_allowance or 0.0)
            + (self.income_professional_allowance or 0.0)
            + (self.income_allowance or 0.0)
            + (self.income_food or 0.0)
            + (self.income_transport or 0.0)
            + (self.income_fuel or 0.0)
            + (self.income_commission or 0.0)
            + (self.income_commission_sale or 0.0)
        )
        return recurring, (self.income_other or 0.0)

    def _bracket_tax(self, taxable, policy):
        """ภาษีจากขั้นบันได — ใช้สำเนาบนสลิปก่อน ถ้าไม่มีค่อยใช้ของนโยบาย"""
        brackets = self.tax_bracket_ids or policy.tax_bracket_ids
        for bracket in sorted(brackets, key=lambda b: b.sequence, reverse=True):
            if taxable > bracket.income_from:
                return (taxable * (bracket.rate / 100.0)) - bracket.deduction
        return 0.0

    def _calculate_tax(self, recurring_income, sso_monthly, one_time_income=0.0,
                       policy=None):
        """ภาษีต่อเดือน + ต่อปี ตามวิธีหัก ณ ที่จ่ายของกรมสรรพากร

        เพดานและอัตราทุกตัวอ่านจากนโยบาย — บริษัทที่เช่าระบบตั้งเองได้
        """
        self.ensure_one()
        policy = policy or self._get_policy()
        annual_income = recurring_income * 12
        sso_annual = min((sso_monthly or 0.0) * 12, policy.sso_tax_deduction_cap or 9000.0)

        provident_annual = 0.0
        if self.provident_fund_rate > 0:
            monthly = (self.base_salary or 0.0) * (self.provident_fund_rate / 100.0)
            provident_annual = min(monthly * 12, policy.ded_pension_fund_max or 500000.0)

        def pct(value):
            return (value or 0.0) / 100.0

        def capped_extras(inc, expense_eff):
            """รวมค่าลดหย่อนเพิ่มเติมหลังบังคับเพดานตามนโยบาย

            ผู้ใช้กรอกเกินเพดานได้ ระบบจะหักให้ไม่เกินที่กำหนดเสมอ
            """
            inc = inc or 0.0
            spouse = min(self.ded_spouse or 0.0, policy.ded_spouse_max)
            parents = min(self.ded_parents or 0.0, policy.ded_parents_max)
            disabled = self.ded_disabled or 0.0

            health_self = min(self.ded_health_insurance or 0.0,
                              policy.ded_health_self_max)
            life_health = min((self.ded_life_insurance or 0.0) + health_self,
                              policy.ded_life_health_max)
            parents_health = min(self.ded_parents_health_insurance or 0.0,
                                 policy.ded_parents_health_max)
            pension_ins = min(self.ded_pension_insurance or 0.0,
                              inc * pct(policy.ded_pension_ins_rate),
                              policy.ded_pension_ins_max)

            rmf = min(self.ded_rmf or 0.0,
                      inc * pct(policy.ded_rmf_rate), policy.ded_rmf_max)
            ssf = min(self.ded_ssf or 0.0,
                      inc * pct(policy.ded_ssf_rate), policy.ded_ssf_max)
            pf_extra = min(self.ded_pension_fund or 0.0,
                           inc * pct(policy.ded_pension_fund_rate),
                           policy.ded_pension_fund_max)
            # เพดานรวมกลุ่มเกษียณ — กองทุนที่หักตามอัตราแล้วกินโควตาไปก่อน
            room = max(0.0, (policy.ded_retire_group_max or 0.0) - provident_annual)
            retire = min(pension_ins + rmf + ssf + pf_extra, room)
            thaiesg = min(self.ded_thaiesg or 0.0,
                          inc * pct(policy.ded_thaiesg_rate), policy.ded_thaiesg_max)

            home_loan = min(self.ded_home_loan_interest or 0.0, policy.ded_home_loan_max)
            shopping = min(self.ded_shopping or 0.0, policy.ded_shopping_max)

            # เงินบริจาคหักได้ไม่เกิน X% ของเงินได้หลังหักลดหย่อนอื่นแล้ว
            base = max(0.0, inc - expense_eff
                       - policy.tax_personal_deduction - self.child_deduction
                       - sso_annual - provident_annual
                       - (spouse + parents + disabled + life_health + parents_health
                          + retire + thaiesg + home_loan + shopping))
            donation_rate = pct(policy.ded_donation_rate)
            edu_donation = min(self.ded_donation_education or 0.0, base * donation_rate)
            gen_donation = min(self.ded_donation or 0.0,
                               (base - edu_donation) * donation_rate)

            return (spouse + parents + disabled + life_health + parents_health
                    + retire + thaiesg + home_loan + shopping
                    + edu_donation + gen_donation)

        def annual_tax(inc):
            expense_eff = min(inc * pct(policy.tax_expense_rate), policy.tax_expense_max)
            extras = capped_extras(inc, expense_eff)
            total_ded = (policy.tax_personal_deduction + self.child_deduction + extras
                         + expense_eff + sso_annual + provident_annual)
            return self._bracket_tax(max(0.0, inc - total_ded), policy)

        tax_no_bonus = annual_tax(annual_income)
        monthly_no_bonus = tax_no_bonus / 12

        if one_time_income > 0:
            tax_with_bonus = annual_tax(annual_income + one_time_income)
            # ภาษีส่วนเพิ่มของรายได้ก้อนเดียว หักทั้งก้อนในเดือนที่จ่าย
            return monthly_no_bonus + (tax_with_bonus - tax_no_bonus), tax_with_bonus
        return monthly_no_bonus, tax_no_bonus

    # ==================================================================
    # เครื่องคำนวณหลัก
    # ==================================================================
    def action_recalculate(self):
        """คำนวณสลิปใหม่ทั้งใบ — ปุ่มเดียวที่ผู้ใช้ต้องกด"""
        for rec in self:
            rec._recalculate()
        return True

    def _recalculate(self):
        self.ensure_one()
        if self.state == 'done':
            raise UserError('สลิปที่ยืนยันแล้วแก้ไม่ได้ — กดย้อนกลับเป็นร่างก่อน')

        employee = self.employee_id
        company = self.company_id or self.env.company
        date_from, date_to = self._cycle_window()
        if not date_from:
            raise UserError('เดือน/ปีของสลิปไม่ถูกต้อง')

        # ล็อกนโยบายที่ใช้ไว้กับสลิป — แก้นโยบายภายหลังจะไม่เปลี่ยนสลิปเก่า
        policy = self.env['payroll.policy'].sudo().get_for(company, date_to)
        self.policy_id = policy.id
        self._snapshot_tax_brackets(policy)

        Engine = self.env['payroll.attendance.engine']
        holidays = self.env['payroll.holiday'].sudo().get_holiday_dates(
            date_to.year, company.id)

        # บังคับคำนวณค่าที่ดึงมาจากโมเดลอื่นใหม่ก่อนเสมอ
        # ฟิลด์พวกนี้เป็น stored compute ที่ depends อยู่กับฟิลด์บนสลิปเท่านั้น
        # จึงไม่รู้ตัวเมื่อมีการเพิ่ม/แก้ "เงินได้อื่นๆ" หรือ "งวดเงินประกัน" ภายหลัง
        self._compute_other_income()
        self._compute_deposit_amounts()

        # ---------- ค่าเที่ยว / เบี้ยเลี้ยงคนขับ ----------
        self._fetch_driver_allowance(date_from, date_to)

        # ---------- OT ----------
        if not self.override_ot and not employee._payroll_skips_ot():
            ot = Engine.compute_overtime(
                employee, date_from, date_to, policy,
                base_salary=self.base_salary,
                rounding=self.ot_calculation_method,
                holidays=holidays)
            self.ot_line_ids.unlink()
            self.ot_line_ids = [(0, 0, {
                'date': line['date'],
                'manual_log_id': line['manual_log_id'],
                'start_time_text': line['start_time_text'],
                'end_time_text': line['end_time_text'],
                'ot_hours': line['ot_hours'],
                'ot_amount': line['ot_amount'],
                'ot_type': line['ot_type'],
                'rate': line['rate'],
            }) for line in ot['lines']]
            self.ot_total_weekday = ot['total_weekday']
            self.ot_total_holiday = ot['total_holiday']
            self.ot_total_sunday = ot['total_sunday']
        ot_amount_total = ((self.ot_total_weekday or 0.0)
                           + (self.ot_total_holiday or 0.0)
                           + (self.ot_total_sunday or 0.0))

        # ---------- สาย / ขาด / ลา ----------
        if not self.manual_override and not employee._payroll_skips_attendance():
            att = Engine.compute_attendance_deductions(
                employee, date_from, date_to, policy,
                grace_period=self.lateness_grace_period,
                base_salary=self.base_salary,
                holidays=holidays)
            self.late_checkin_minutes = att['late_minutes']
            self.early_checkout_minutes = att['early_minutes']
            self.lateness_minutes = att['total_lateness_minutes']
            self.missed_days = att['missed_days']
            self.working_days = att['working_days']
            self.present_days = att['present_days']
            self.missed_days_detail = ', '.join(att['missed_log'])
            self.leave_deduction_total = att['leave_deduction_total']
            self.late_checkin_deduction = att['late_deduction']
            self.early_checkout_deduction = att['early_deduction']
            # ยอดหักขาดงานรวมออกก่อนเวลาไว้แล้ว — ห้ามบวกซ้ำตอนรวมยอด
            self.deduction_absent = att['absent_deduction_total']
            self.missed_days_deduction = att['absent_deduction_total']
            self.deduction_late = att['late_deduction']
            self.deduction_leave = att['leave_deduction_total']
            self.lateness_deduction = (self.deduction_late + self.deduction_leave
                                       + self.deduction_absent)
            self._rebuild_deduction_lines(att)

        # ---------- ประกันสังคม ----------
        # ลำดับความสำคัญ: บุคคลพิเศษ → ปรับด้วยมือบนสลิป → คำนวณตามนโยบาย
        prorated = self._prorated_salary(policy)
        sso_base = 0.0
        sso_locked, sso_locked_amount = employee._payroll_sso_override()
        if sso_locked:
            sso_amount = sso_locked_amount
        elif not policy.sso_enabled or not employee.enable_social_security:
            sso_amount = 0.0
        elif self.manual_override_sso or (self.manual_sso_amount or 0) > 0:
            sso_amount = self.manual_sso_amount
        else:
            wage = prorated if policy.sso_prorate_with_salary else (self.base_salary or 0.0)
            sso_base = max(policy.sso_min_wage, min(wage, policy.sso_max_wage))
            sso_amount = float(round_half_up(sso_base * (policy.sso_rate / 100.0)))
        self.sso_total = sso_amount
        self.sso_base_used = sso_base

        # ---------- ภาษี ----------
        tax_locked, tax_locked_amount = employee._payroll_tax_override()
        if tax_locked:
            tax_amount, tax_annual = tax_locked_amount, tax_locked_amount * 12
        elif not policy.tax_enabled or not employee.enable_tax:
            tax_amount, tax_annual = 0.0, 0.0
        elif self.manual_override_tax:
            tax_amount, tax_annual = self.manual_tax_amount, self.manual_tax_amount * 12
        else:
            recurring, one_time = self._tax_income_base(ot_amount=ot_amount_total)
            tax_amount, tax_annual = self._calculate_tax(
                recurring, sso_amount, one_time, policy=policy)
        self.tax_monthly = tax_amount
        self.tax_annual = tax_annual

        # ---------- บรรทัดสลิป ----------
        if not self.manual_override:
            self.line_ids.unlink()
            self.line_ids = [(0, 0, vals) for vals in self._build_lines(
                prorated, sso_amount, tax_amount)]
        return True

    def _build_lines(self, prorated_salary, sso_amount, tax_amount):
        """บรรทัดในสลิป — ชื่อบรรทัดคงเดิมจาก Odoo 14 เพราะแอปและรายงานอ้างชื่อนี้"""
        self.ensure_one()
        income = [
            ('เงินเดือน', prorated_salary),
            ('ค่าล่วงเวลา/โอที', self.ot_total_weekday),
            ('ค่าล่วงเวลา/วันหยุดนักขัตฤกษ์', self.ot_total_holiday),
            ('ค่าล่วงเวลา', self.ot_total_sunday),
            ('เงินค่าครองชีพ', self.income_cost_of_living),
            ('เงินประจำตำแหน่ง', self.income_position_allowance),
            ('เงินค่าประสบการณ์', self.income_experience_allowance),
            ('เงินค่าวิชาชีพ', self.income_professional_allowance),
            ('เบี้ยเลี้ยง นอกสถานที่', self.income_allowance),
            ('ค่าอาหาร', self.income_food),
            ('ค่าเดินทาง', self.income_transport),
            ('อินเซนทีฟ', self.income_fuel),
            ('ค่าคอมมิชชั่น',
             (self.income_commission or 0.0) + (self.income_commission_sale or 0.0)),
            ('รายได้อื่นๆ', self.income_other),
        ]
        deduction = [
            ('กองทุนสำรองเลี้ยงชีพ', self.expense_provident),
            ('เบิกเงินล่วงหน้า', self.expense_advance),
            ('เงินกู้', self.expense_loan),
            ('กยศ', self.expense_ksl),
            ('หักเงินอื่นๆ', self.expense_other),
            ('หักสาย', self.deduction_late),
            ('หักลากิจ', self.deduction_leave),
            ('หักขาดงาน', self.missed_days_deduction),
            ('ประกันสังคม', sso_amount),
            ('ภาษีหัก ณ ที่จ่าย', tax_amount),
        ]
        if self.provident_fund_rate > 0:
            deduction.insert(0, (
                'กองทุนสำรองเลี้ยงชีพ (ตามอัตรา)',
                (self.base_salary or 0.0) * (self.provident_fund_rate / 100.0)))

        vals = []
        for sequence, (name, amount) in enumerate(income, start=1):
            vals.append({'name': name, 'type': 'income',
                         'amount': amount or 0.0, 'sequence': sequence * 10})
        for sequence, (name, amount) in enumerate(deduction, start=1):
            vals.append({'name': name, 'type': 'deduction',
                         'amount': amount or 0.0, 'sequence': 1000 + sequence * 10})
        return vals

    def _rebuild_deduction_lines(self, att):
        """ตารางแจกแจงว่าหักอะไร วันไหน กี่นาที เป็นเงินเท่าไร"""
        self.ensure_one()
        self.deduction_line_ids.unlink()
        per_minute = att['rate_per_minute']
        per_day = att['rate_per_day']
        vals = []
        for entry in att['late_log']:
            vals.append({
                'date': entry['date'], 'kind': 'late',
                'detail': 'เข้า %s (กะเริ่ม %s)' % (entry['checkin'], entry['shift_start']),
                'minutes': entry['minutes'],
                'amount': round_half_up(entry['minutes'] * per_minute),
            })
        for entry in att['early_log']:
            vals.append({
                'date': entry['date'], 'kind': 'early',
                'detail': 'ออก %s (กะเลิก %s)' % (entry['checkout'], entry['shift_end']),
                'minutes': entry['minutes'],
                'amount': round_half_up(entry['minutes'] * per_minute),
            })
        for entry in att['leave_log']:
            vals.append({
                'date': entry['date'], 'kind': 'leave',
                'detail': '%s %s-%s' % (entry['type'], entry['start'], entry['end']),
                'minutes': 0.0, 'amount': entry['deduction'],
            })
        for day in att['missed_log']:
            vals.append({
                'date': day, 'kind': 'absent', 'detail': 'ขาดงานเต็มวัน',
                'minutes': 0.0, 'amount': round_half_up(per_day),
            })
        self.deduction_line_ids = [(0, 0, v) for v in sorted(vals, key=lambda v: v['date'])]

    def _fetch_driver_allowance(self, date_from, date_to):
        """ค่าเที่ยว + เบี้ยเลี้ยงคนขับจากงานขนส่ง/เช่า

        Odoo 14 ต้อง login ข้ามเซิร์ฟเวอร์ไป npd-solution.com แล้วดึง JSON
        มาเทียบเอง — ตอนนี้อยู่ DB เดียวกันจึงอ่านผ่าน ORM ได้ตรง
        ยึด ``delivery_date`` (วันส่งจริงเวลาไทย ที่ store ไว้แล้ว) และไม่กรองสาขา
        """
        self.ensure_one()
        if self.manual_override:
            return
        if 'vehicle.booking' not in self.env or 'vehicle.driver' not in self.env:
            return
        code = (self.employee_code or '').strip()
        if not code:
            return
        driver = self.env['vehicle.driver'].sudo().search(
            [('employee_code', '=', code)], limit=1)
        if not driver:
            return
        bookings = self.env['vehicle.booking'].sudo().search([
            ('driver_id', '=', driver.id),
            ('state', '=', 'done'),
            ('delivery_date', '>=', date_from),
            ('delivery_date', '<=', date_to),
        ])
        trip = sum(bookings.mapped('travel_expenses'))
        allowance = sum(bookings.mapped('daily_allowance'))
        self.income_transport_trip = trip
        self.income_transport_allowance = allowance
        _logger.info(
            '[DRIVER ALLOWANCE] emp=%s driver=%s งาน=%d ค่าเที่ยว=%.2f เบี้ยเลี้ยง=%.2f',
            code, driver.name, len(bookings), trip, allowance)

    # ==================================================================
    # CRUD / ปุ่ม
    # ==================================================================
    def _snapshot_tax_brackets(self, policy):
        """คัดลอกขั้นภาษีจากนโยบายมาเก็บไว้กับสลิป

        ทำให้แก้นโยบายภายหลัง (เช่นกฎหมายเปลี่ยน) ไม่ย้อนไปเปลี่ยนสลิปที่ออกไปแล้ว
        """
        self.ensure_one()
        if self.tax_bracket_ids:
            return
        self.tax_bracket_ids = [(0, 0, {
            'sequence': bracket.sequence,
            'income_from': bracket.income_from,
            'income_to': bracket.income_to,
            'rate': bracket.rate,
            'deduction': bracket.deduction,
        }) for bracket in policy.tax_bracket_ids]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.env.context.get('skip_payroll_recalculate'):
                try:
                    record._recalculate()
                except Exception as exc:
                    _logger.warning('[PAYROLL] คำนวณครั้งแรกล้มเหลว emp=%s: %s',
                                    record.employee_code, exc)
        return records

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError('ยังไม่มีรายละเอียดเงินเดือน — กดคำนวณใหม่ก่อน')
            rec.state = 'done'
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_generate_next_month(self):
        """สร้างสลิปเดือนถัดไปโดยคัดลอกค่าตั้งต้น (โบนัส/เงินตกหล่นรีเซ็ต)"""
        for rec in self:
            current = date(int(rec.year), rec.month, 1)
            following = current + relativedelta(months=1)
            existing = self.sudo().search([
                ('employee_id', '=', rec.employee_id.id),
                ('month', '=', following.month),
                ('year', '=', str(following.year)),
            ], limit=1)
            if existing:
                continue
            rec.copy({
                'month': following.month,
                'year': str(following.year),
                'line_ids': [], 'ot_line_ids': [], 'deduction_line_ids': [],
                'bonus_active': False,
                'income_bonus': 0.0,
                'income_missed_payment': 0.0,
                'state': 'draft',
            })
        return True

    # ==================================================================
    # API สำหรับแอป (แทน get_payslip_data.php)
    # ==================================================================
    def _company_address_line(self):
        """ที่อยู่บริษัทบรรทัดเดียวสำหรับหัวกระดาษสลิป"""
        self.ensure_one()
        partner = self.company_id.partner_id
        parts = [partner.street, partner.street2, partner.city,
                 partner.state_id.name, partner.zip]
        address = ' '.join(p for p in parts if p)
        contacts = []
        if partner.phone:
            contacts.append('โทร. %s' % partner.phone)
        if partner.email:
            contacts.append(partner.email)
        if contacts:
            address = ('%s  %s' % (address, ' / '.join(contacts))).strip()
        return address

    def _as_payslip_dict(self):
        """รูปแบบเดียวกับ get_payslip_data.php เดิม รวมกลุ่ม incomes/deductions"""
        self.ensure_one()
        employee = self.employee_id
        incomes = [
            {'label': 'เงินเดือน', 'amount': self._line_amount('เงินเดือน')},
            {'label': 'เงินประจำตำแหน่ง', 'amount': self.income_position_allowance},
            {'label': 'ค่าประสบการณ์', 'amount': self.income_experience_allowance},
            {'label': 'ค่าวิชาชีพ', 'amount': self.income_professional_allowance},
            {'label': 'ค่าครองชีพ', 'amount': self.income_cost_of_living},
            {'label': 'ค่าล่วงเวลา/โอที', 'amount': self.ot_total_weekday},
            {'label': 'ค่าล่วงเวลา/วันหยุดนักขัตฤกษ์', 'amount': self.ot_total_holiday},
            {'label': 'ค่าล่วงเวลา', 'amount': self.ot_total_sunday},
            {'label': 'เบี้ยเลี้ยง', 'amount': self.income_allowance},
            {'label': 'ค่าอาหาร', 'amount': self.income_food},
            {'label': 'ค่าเดินทาง/ค่าเที่ยว', 'amount': self.income_transport},
            {'label': 'อินเซนทีฟ', 'amount': self.income_fuel},
            {'label': 'คอมมิชชั่น',
             'amount': (self.income_commission or 0.0) + (self.income_commission_sale or 0.0)},
            {'label': 'รายได้อื่นๆ', 'amount': self.income_other},
        ]
        deductions = [
            {'label': 'สาย', 'amount': self.deduction_late},
            {'label': 'ลากิจ', 'amount': self.deduction_leave},
            {'label': 'ขาดงาน', 'amount': self.missed_days_deduction},
            {'label': 'ภาษีหัก ณ ที่จ่าย', 'amount': self.tax_monthly},
            {'label': 'ประกันสังคม', 'amount': self.sso_total},
            {'label': 'กองทุนสำรองเลี้ยงชีพ', 'amount': self.expense_provident},
            {'label': 'กยศ.', 'amount': self.expense_ksl},
            {'label': 'เบิกเงินล่วงหน้า', 'amount': self.expense_advance},
            {'label': 'เงินกู้', 'amount': self.expense_loan},
            {'label': 'หักอื่นๆ', 'amount': self.expense_other},
        ]
        return {
            'id': self.id,
            'employee_id': employee.id,
            'employee_code': self.employee_code or '',
            'full_name': employee.full_name or '',
            'branch': self.branch_id.name or '',
            'department': self.department_id.name or '',
            'position': self.position_id.name or '',
            'company': self.company_id.name or '',
            # ที่อยู่หัวกระดาษสลิป — ส่งมาจากบริษัทจริงของพนักงาน
            # แอปเคยเก็บชื่อ/ที่อยู่บริษัททั้งกลุ่มไว้ในโค้ดแล้วจับคู่จากชื่อ
            # ซึ่งจับไม่ตรงและพิมพ์บริษัทผิดทุกใบ ยิ่งตอนปล่อยเช่าจะกลายเป็น
            # สลิปของลูกค้าขึ้นหัวกระดาษเป็นบริษัทเรา
            'company_address': self._company_address_line(),
            'bank_account_number': employee.bank_account_number or '',
            'month': self.month,
            'year': self.year,
            'payment_date': self.payment_date.isoformat() if self.payment_date else '',
            'base_salary': self.base_salary or 0.0,
            'total_gross': self.total_gross or 0.0,
            'total_deduction': self.total_deduction or 0.0,
            'net_salary': self.net_salary or 0.0,
            'ot_total': self.ot_total or 0.0,
            'ot_total_weekday': self.ot_total_weekday or 0.0,
            'ot_total_holiday': self.ot_total_holiday or 0.0,
            'ot_total_sunday': self.ot_total_sunday or 0.0,
            'sso_total': self.sso_total or 0.0,
            'tax_monthly': self.tax_monthly or 0.0,
            'lateness_deduction': self.lateness_deduction or 0.0,
            'missed_days_deduction': self.missed_days_deduction or 0.0,
            'accumulated_income': self.accumulated_income or 0.0,
            'accumulated_vat': self.accumulated_vat or 0.0,
            'accumulated_social_security': self.accumulated_social_security or 0.0,
            'provident_fund_rate': self.provident_fund_rate or 0.0,
            'incomes': incomes,
            'deductions': deductions,
        }

    def _line_amount(self, name):
        line = self.line_ids.filtered(lambda l: l.name == name)[:1]
        return line.amount if line else 0.0

    @api.model
    def api_get_payslips(self, employee_code, month=None, year=None):
        """สลิปของพนักงาน เรียงใหม่ไปเก่า — เห็นเฉพาะที่ยืนยันแล้ว

        ของเดิมส่งสลิปทุกใบรวมที่ยังเป็นร่าง ทำให้พนักงานเห็นยอดที่ยังไม่นิ่ง
        """
        employee = self.env['employee.salary']._find_by_code(employee_code)
        if not employee:
            return []
        domain = [('employee_id', '=', employee.id), ('state', '=', 'done')]
        if month:
            domain.append(('month', '=', int(month)))
        if year:
            domain.append(('year', '=', str(year)))
        records = self.sudo().search(domain, order='year desc, month desc')
        return [rec._as_payslip_dict() for rec in records]


class PayrollSalaryLine(models.Model):
    _name = 'payroll.salary.line'
    _description = 'รายละเอียดเงินเดือน'
    _order = 'sequence, id'

    payroll_id = fields.Many2one(
        'payroll.salary', string='สลิปเงินเดือน', required=True, ondelete='cascade')
    sequence = fields.Integer(string='ลำดับ', default=10)
    name = fields.Char(string='รายการ', required=True)
    type = fields.Selection([
        ('income', 'รายได้'),
        ('deduction', 'รายการหัก'),
    ], string='ประเภท', required=True)
    amount = fields.Float(string='จำนวนเงิน')


class PayrollOtLine(models.Model):
    _name = 'payroll.ot.line'
    _description = 'รายการค่าล่วงเวลา'
    _order = 'date, id'

    payroll_id = fields.Many2one(
        'payroll.salary', string='สลิปเงินเดือน', required=True, ondelete='cascade')
    manual_log_id = fields.Many2one(
        'hr.manual.time.log', string='คำขอเพิ่มเวลา', ondelete='set null')
    date = fields.Date(string='วันที่', required=True)
    start_time_text = fields.Char(string='เวลาเริ่ม')
    end_time_text = fields.Char(string='เวลาสิ้นสุด')
    ot_hours = fields.Float(string='ชั่วโมง OT')
    rate = fields.Float(string='อัตรา (เท่า)')
    ot_amount = fields.Float(string='จำนวนเงิน')
    ot_type = fields.Selection([
        ('weekday', 'วันทำงาน (นอกกะ)'),
        ('sunday', 'วันหยุดประจำสัปดาห์'),
        ('holiday', 'วันหยุดนักขัตฤกษ์'),
    ], string='ประเภท OT', required=True)


class PayrollDeductionLine(models.Model):
    _name = 'payroll.deduction.line'
    _description = 'แจกแจงการหักรายวัน'
    _order = 'date, id'

    payroll_id = fields.Many2one(
        'payroll.salary', string='สลิปเงินเดือน', required=True, ondelete='cascade')
    date = fields.Date(string='วันที่', required=True)
    kind = fields.Selection([
        ('late', 'เข้าสาย'),
        ('early', 'ออกก่อนเวลา'),
        ('leave', 'ลา'),
        ('absent', 'ขาดงาน'),
    ], string='ประเภท', required=True)
    detail = fields.Char(string='รายละเอียด')
    minutes = fields.Float(string='นาที')
    amount = fields.Float(string='ยอดหัก')


class PayrollTaxBracket(models.Model):
    _name = 'payroll.tax.bracket'
    _description = 'ขั้นบันไดอัตราภาษี'
    _order = 'sequence'

    payroll_id = fields.Many2one(
        'payroll.salary', string='สลิปเงินเดือน', ondelete='cascade')
    sequence = fields.Integer(string='ลำดับ', required=True)
    income_from = fields.Float(string='เงินได้ตั้งแต่', required=True)
    income_to = fields.Float(string='ถึง', required=True)
    rate = fields.Float(string='อัตราภาษี (%)', required=True)
    deduction = fields.Float(
        string='ค่าลดหย่อนของขั้น',
        help='ใช้ในสูตรย่อ: (เงินได้สุทธิ × อัตรา) − ค่านี้')
