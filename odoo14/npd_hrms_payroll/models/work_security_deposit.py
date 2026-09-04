# -*- coding: utf-8 -*-
"""เงินประกันการทำงาน

หักจากเงินเดือนพนักงานเป็นงวดจนครบวงเงิน แล้วคืนให้เมื่อลาออกอย่างถูกต้อง
มีสองประเภทการหักที่คิดคนละแบบ:

  * **หักรายเดือน (regular)** — เงินประกันการทำงานปกติ ลาออกแล้วต้องคืน
  * **หัก Work Permit / อื่นๆ (extra)** — ค่าใช้จ่ายที่บริษัทออกให้ก่อน
    ลาออกแล้วไม่คืน (เป็นค่าใช้จ่ายจริงที่เกิดขึ้นแล้ว)

ยึด "รอบตัดเงินเดือน" ไม่ใช่เดือนปฏิทิน — งวดที่ payment_date อยู่ในรอบไหน
ก็เข้าสลิปรอบนั้น
"""
import logging

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class WorkSecurityDeposit(models.Model):
    _name = 'work.security.deposit'
    _description = 'เงินประกันการทำงาน'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char(
        string='ชื่อรายการ', compute='_compute_name', store=True, readonly=True)
    branch_id = fields.Many2one('res.branch', string='สาขา', required=True)
    department_ids = fields.Many2many(
        'hr.department.custom', string='แผนกที่บังคับใช้',
        help='เว้นว่าง = ทุกแผนกในสาขานี้')
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)

    default_amount = fields.Float(
        string='วงเงินประกัน (บาท)', default=5000.0, required=True)
    default_months = fields.Integer(
        string='จำนวนงวดที่หัก', default=3, required=True)
    default_monthly_amount = fields.Float(
        string='หักงวดละ (บาท)', compute='_compute_default_monthly', store=True)

    line_ids = fields.One2many(
        'work.security.deposit.line', 'deposit_id', string='รายการพนักงาน')
    employee_count = fields.Integer(
        string='จำนวนพนักงาน', compute='_compute_employee_count')

    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('confirmed', 'ยืนยันแล้ว'),
        ('cancelled', 'ยกเลิก'),
    ], string='สถานะ', default='draft', required=True, tracking=True)
    note = fields.Text(string='หมายเหตุ')

    @api.depends('branch_id', 'default_amount')
    def _compute_name(self):
        for rec in self:
            branch = rec.branch_id.name or '-'
            rec.name = 'เงินประกันการทำงาน %s (%s บาท)' % (branch, rec.default_amount)

    @api.depends('default_amount', 'default_months')
    def _compute_default_monthly(self):
        for rec in self:
            rec.default_monthly_amount = (
                rec.default_amount / rec.default_months
                if rec.default_months else 0.0)

    @api.depends('line_ids')
    def _compute_employee_count(self):
        for rec in self:
            rec.employee_count = len(rec.line_ids)

    @api.constrains('default_months')
    def _check_months(self):
        for rec in self:
            if rec.default_months <= 0:
                raise ValidationError('จำนวนงวดที่หักต้องมากกว่า 0')

    # ------------------------------------------------------------------
    def action_pull_employees(self):
        """ดึงพนักงานในสาขา/แผนกที่กำหนดมาสร้างรายการหัก (ข้ามคนที่มีแล้ว)"""
        Line = self.env['work.security.deposit.line']
        for rec in self:
            domain = [
                ('branch_id', '=', rec.branch_id.id),
                ('company_id', '=', rec.company_id.id),
                ('status', '=', 'active'),
            ]
            if rec.department_ids:
                domain.append(('department_id', 'in', rec.department_ids.ids))
            employees = self.env['employee.salary'].sudo().search(domain)
            existing = set(rec.line_ids.mapped('employee_id').ids)
            for employee in employees:
                if employee.id in existing:
                    continue
                Line.create({
                    'deposit_id': rec.id,
                    'employee_id': employee.id,
                    'start_work_date': employee.start_date or fields.Date.context_today(self),
                    'total_amount': rec.default_amount,
                    'deduction_months': rec.default_months,
                })
        return True

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError('ยังไม่มีรายการพนักงาน')
            rec.state = 'confirmed'
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return True

    # ------------------------------------------------------------------
    # ที่ payroll เรียกใช้
    # ------------------------------------------------------------------
    @api.model
    def get_cycle_amounts(self, employee, date_from, date_to):
        """ยอดหัก/คืนของพนักงานคนนี้ในรอบตัดที่ระบุ

        คืน dict: regular = หักรายเดือน, extra = หัก Work Permit,
                  refund = เงินที่ต้องคืนเพราะลาออก
        """
        result = {'regular': 0.0, 'extra': 0.0, 'refund': 0.0}
        if not employee:
            return result

        payments = self.env['work.security.deposit.line.payment'].sudo().search([
            ('employee_id', '=', employee.id),
            ('deposit_state', '=', 'confirmed'),
            ('payment_date', '>=', date_from),
            ('payment_date', '<=', date_to),
        ])
        for payment in payments:
            if payment.payment_type == 'work_permit':
                result['extra'] += payment.amount
            else:
                result['regular'] += payment.amount

        # คืนเงินประกัน — เฉพาะรอบที่วันลาออกตกอยู่ในรอบนี้ และยังไม่เคยคืน
        if employee.resign_date and date_from <= employee.resign_date <= date_to:
            lines = self.env['work.security.deposit.line'].sudo().search([
                ('employee_id', '=', employee.id),
                ('deposit_id.state', '=', 'confirmed'),
                ('refund_status', '=', 'pending'),
            ])
            result['refund'] = sum(lines.mapped('refund_amount'))
        return result


class WorkSecurityDepositLine(models.Model):
    _name = 'work.security.deposit.line'
    _description = 'เงินประกันการทำงาน (รายบุคคล)'
    _order = 'employee_code'
    _rec_name = 'employee_id'

    deposit_id = fields.Many2one(
        'work.security.deposit', string='รายการ', required=True, ondelete='cascade')
    state = fields.Selection(
        related='deposit_id.state', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', related='deposit_id.company_id', store=True, readonly=True)

    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True, ondelete='cascade')
    employee_code = fields.Char(
        related='employee_id.employee_code', store=True, readonly=True, index=True)
    firstname = fields.Char(related='employee_id.firstname', store=True, readonly=True)
    lastname = fields.Char(related='employee_id.lastname', store=True, readonly=True)
    employee_branch_id = fields.Many2one(
        'res.branch', related='employee_id.branch_id', store=True, readonly=True)
    employee_department_id = fields.Many2one(
        'hr.department.custom', related='employee_id.department_id',
        store=True, readonly=True)
    employee_status = fields.Selection(
        related='employee_id.status', store=True, readonly=True)

    start_work_date = fields.Date(string='วันที่เริ่มงาน', required=True)
    total_amount = fields.Float(string='วงเงินประกัน (บาท)', required=True, default=5000.0)
    deduction_months = fields.Integer(string='จำนวนงวด', default=3, required=True)
    monthly_amount = fields.Float(
        string='หักงวดละ', compute='_compute_monthly_amount', store=True)
    skip_deduction = fields.Boolean(
        string='ยกเว้นไม่หัก', help='ใช้กับพนักงานที่ตกลงไม่ต้องวางเงินประกัน')

    payment_ids = fields.One2many(
        'work.security.deposit.line.payment', 'line_id',
        string='งวดการหัก', domain=[('payment_type', '=', 'regular')])
    work_permit_payment_ids = fields.One2many(
        'work.security.deposit.line.payment', 'line_id',
        string='งวดหัก Work Permit', domain=[('payment_type', '=', 'work_permit')])
    is_work_permit = fields.Boolean(string='มีค่า Work Permit')
    work_permit_total = fields.Float(string='ยอด Work Permit รวม')

    deducted_amount = fields.Float(
        string='หักไปแล้ว (บาท)', compute='_compute_deducted', store=True)
    months_deducted = fields.Integer(
        string='หักไปแล้ว (งวด)', compute='_compute_deducted', store=True)
    refund_amount = fields.Float(
        string='ยอดที่ต้องคืน', compute='_compute_deducted', store=True,
        help='คืนเฉพาะเงินประกันรายเดือน — ค่า Work Permit ไม่คืน')

    work_status = fields.Selection([
        ('working', 'ทำงานอยู่'),
        ('resigned', 'ออกจากงาน'),
        ('transferred', 'ย้ายสาขา'),
    ], string='สถานะการทำงาน', default='working', required=True)
    resign_date = fields.Date(string='วันที่ออกจากงาน')
    refund_status = fields.Selection([
        ('none', 'ไม่ต้องคืน'),
        ('pending', 'รอคืนเงิน'),
        ('refunded', 'คืนแล้ว'),
    ], string='สถานะการคืนเงิน', compute='_compute_refund_status', store=True)
    refund_payroll_id = fields.Many2one(
        'payroll.salary', string='คืนในสลิป', readonly=True, ondelete='set null')
    manual_refunded = fields.Boolean(string='คืนด้วยเงินสด/โอน (นอกสลิป)')
    manual_refunded_date = fields.Date(string='วันที่คืน')
    manual_refunded_note = fields.Char(string='หมายเหตุการคืน')

    _sql_constraints = [
        ('employee_deposit_uniq', 'unique(deposit_id, employee_id)',
         'พนักงานคนนี้มีอยู่ในรายการนี้แล้ว'),
    ]

    @api.depends('total_amount', 'deduction_months')
    def _compute_monthly_amount(self):
        for rec in self:
            rec.monthly_amount = (
                rec.total_amount / rec.deduction_months
                if rec.deduction_months else 0.0)

    @api.depends('payment_ids.amount', 'payment_ids.is_deducted')
    def _compute_deducted(self):
        for rec in self:
            done = rec.payment_ids.filtered('is_deducted')
            rec.deducted_amount = sum(done.mapped('amount'))
            rec.months_deducted = len(done)
            # คืนเฉพาะเงินประกันรายเดือนที่หักไปแล้ว
            rec.refund_amount = rec.deducted_amount

    @api.depends('work_status', 'manual_refunded', 'refund_payroll_id',
                 'deducted_amount')
    def _compute_refund_status(self):
        for rec in self:
            if rec.work_status != 'resigned' or rec.deducted_amount <= 0:
                rec.refund_status = 'none'
            elif rec.manual_refunded or rec.refund_payroll_id:
                rec.refund_status = 'refunded'
            else:
                rec.refund_status = 'pending'

    # ------------------------------------------------------------------
    def action_generate_schedule(self):
        """สร้างงวดการหักตามจำนวนงวด เริ่มเดือนถัดจากวันเริ่มงาน"""
        Payment = self.env['work.security.deposit.line.payment']
        for rec in self:
            if rec.skip_deduction:
                continue
            rec.payment_ids.filtered(lambda p: not p.is_deducted).unlink()
            start = (rec.start_work_date or fields.Date.context_today(self))
            for index in range(rec.deduction_months):
                Payment.create({
                    'line_id': rec.id,
                    'payment_type': 'regular',
                    'payment_date': start + relativedelta(months=index + 1),
                    'amount': rec.monthly_amount,
                })
        return True

    def action_mark_resigned(self):
        """ทำเครื่องหมายว่าลาออก — ระบบจะคำนวณยอดคืนให้อัตโนมัติ"""
        for rec in self:
            rec.write({
                'work_status': 'resigned',
                'resign_date': rec.employee_id.resign_date
                or fields.Date.context_today(self),
            })
            # งวดที่ยังไม่ถึงกำหนด ไม่ต้องหักต่อ
            rec.payment_ids.filtered(lambda p: not p.is_deducted).unlink()
        return True


class WorkSecurityDepositLinePayment(models.Model):
    _name = 'work.security.deposit.line.payment'
    _description = 'งวดการหักเงินประกัน'
    _order = 'payment_date, id'

    line_id = fields.Many2one(
        'work.security.deposit.line', string='รายการเงินประกัน',
        required=True, ondelete='cascade')
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', related='line_id.employee_id',
        store=True, readonly=True, index=True)
    company_id = fields.Many2one(
        'res.company', related='line_id.company_id', store=True, readonly=True)
    deposit_state = fields.Selection(
        related='line_id.deposit_id.state', store=True, readonly=True, index=True)

    payment_type = fields.Selection([
        ('regular', 'เงินประกันรายเดือน'),
        ('work_permit', 'Work Permit / อื่นๆ'),
    ], string='ประเภท', required=True, default='regular')
    payment_date = fields.Date(
        string='เดือนที่หัก', required=True, index=True,
        default=fields.Date.context_today)
    amount = fields.Float(string='จำนวนเงิน (บาท)', required=True, default=0.0)
    is_deducted = fields.Boolean(
        string='หักแล้ว', default=False,
        help='ระบบติ๊กให้เมื่อยอดนี้เข้าสลิปเงินเดือนที่ยืนยันแล้ว')
    payroll_id = fields.Many2one(
        'payroll.salary', string='สลิปที่หัก', readonly=True, ondelete='set null')
