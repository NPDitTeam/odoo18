# -*- coding: utf-8 -*-
"""ฟิลด์เตรียมข้อมูลสำหรับพิมพ์สลิปเงินเดือนด้วย Jasper

Jasper ในระบบนี้อ่านค่าจากฟิลด์ของเรคคอร์ดโดยตรง (ไม่ได้ยิง SQL เอง) ค่าที่ต้อง
จัดรูปก่อนพิมพ์ เช่น เดือนภาษาไทยหรือตัวเลขมีลูกน้ำ จึงต้องเตรียมไว้ที่นี่
ไม่ใช่ไปทำใน template

ทำไมจัดรูปตัวเลขเป็นข้อความตั้งแต่ฝั่ง Odoo
------------------------------------------
ถ้าส่งตัวเลขดิบไปให้ Jasper จัดรูปเอง ผลจะขึ้นกับ locale ของ Jasper server
ซึ่งคุมยาก — จัดที่นี่ทีเดียวจบ และได้รูปแบบตรงกับสลิปที่แอปออกให้พนักงานเป๊ะ

ช่องที่ยอดเป็นศูนย์พิมพ์เป็นช่องว่าง ไม่ใช่ "0.00" ตามฟอร์มเดิม เพื่อให้เห็นชัด
ว่าเดือนนั้นมีรายการอะไรจริงบ้าง
"""
from odoo import models, fields, api

THAI_MONTHS = {
    1: 'มกราคม', 2: 'กุมภาพันธ์', 3: 'มีนาคม', 4: 'เมษายน',
    5: 'พฤษภาคม', 6: 'มิถุนายน', 7: 'กรกฎาคม', 8: 'สิงหาคม',
    9: 'กันยายน', 10: 'ตุลาคม', 11: 'พฤศจิกายน', 12: 'ธันวาคม',
}


def _fmt(amount):
    """จัดรูปเงิน — ศูนย์ให้เป็นช่องว่างตามฟอร์มเดิม"""
    return '{:,.2f}'.format(amount) if amount else ''


class PayrollSalary(models.Model):
    _inherit = 'payroll.salary'

    # ------------------------------------------------------------------
    # หัวกระดาษ
    # ------------------------------------------------------------------
    jasper_company_name = fields.Char(compute='_compute_jasper_header')
    jasper_company_address = fields.Char(compute='_compute_jasper_header')
    jasper_company_logo = fields.Binary(compute='_compute_jasper_header')
    jasper_employee_code = fields.Char(compute='_compute_jasper_header')
    jasper_employee_name = fields.Char(compute='_compute_jasper_header')
    jasper_department = fields.Char(compute='_compute_jasper_header')
    jasper_position = fields.Char(compute='_compute_jasper_header')
    jasper_branch = fields.Char(compute='_compute_jasper_header')
    jasper_period_thai = fields.Char(compute='_compute_jasper_header')
    jasper_payment_date = fields.Char(compute='_compute_jasper_header')
    jasper_bank_account = fields.Char(compute='_compute_jasper_header')
    jasper_printed_by = fields.Char(compute='_compute_jasper_header')

    # ------------------------------------------------------------------
    # คอลัมน์รายได้
    # ------------------------------------------------------------------
    jasper_income_salary = fields.Char(compute='_compute_jasper_income')
    jasper_income_position = fields.Char(compute='_compute_jasper_income')
    jasper_income_experience = fields.Char(compute='_compute_jasper_income')
    jasper_income_professional = fields.Char(compute='_compute_jasper_income')
    jasper_income_cost_living = fields.Char(compute='_compute_jasper_income')
    jasper_income_ot_weekday = fields.Char(compute='_compute_jasper_income')
    jasper_income_ot_holiday = fields.Char(compute='_compute_jasper_income')
    jasper_income_ot_sunday = fields.Char(compute='_compute_jasper_income')
    jasper_income_allowance = fields.Char(compute='_compute_jasper_income')
    jasper_income_food = fields.Char(compute='_compute_jasper_income')
    jasper_income_transport = fields.Char(compute='_compute_jasper_income')
    jasper_income_trip = fields.Char(compute='_compute_jasper_income')
    jasper_income_commission = fields.Char(compute='_compute_jasper_income')
    jasper_income_other = fields.Char(compute='_compute_jasper_income')
    jasper_total_income = fields.Char(compute='_compute_jasper_income')

    # ------------------------------------------------------------------
    # คอลัมน์รายการหัก
    # ------------------------------------------------------------------
    jasper_ded_late = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_leave = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_absent = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_tax = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_sso = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_provident = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_ksl = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_advance = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_loan = fields.Char(compute='_compute_jasper_deduction')
    jasper_ded_other = fields.Char(compute='_compute_jasper_deduction')
    jasper_total_deduction = fields.Char(compute='_compute_jasper_deduction')

    # ------------------------------------------------------------------
    # แถบสรุปท้ายใบ
    # ------------------------------------------------------------------
    jasper_accum_income = fields.Char(compute='_compute_jasper_summary')
    jasper_accum_tax = fields.Char(compute='_compute_jasper_summary')
    jasper_accum_sso = fields.Char(compute='_compute_jasper_summary')
    jasper_net_salary = fields.Char(compute='_compute_jasper_summary')

    # ------------------------------------------------------------------
    @api.depends('base_salary', 'income_position_allowance',
                 'income_experience_allowance', 'income_professional_allowance',
                 'income_cost_of_living', 'ot_total_weekday', 'ot_total_holiday',
                 'ot_total_sunday', 'income_allowance', 'income_food',
                 'income_transport', 'income_transport_trip',
                 'income_commission', 'income_other', 'total_gross')
    def _compute_jasper_income(self):
        for rec in self:
            rec.jasper_income_salary = _fmt(rec.base_salary)
            rec.jasper_income_position = _fmt(rec.income_position_allowance)
            rec.jasper_income_experience = _fmt(rec.income_experience_allowance)
            rec.jasper_income_professional = _fmt(rec.income_professional_allowance)
            rec.jasper_income_cost_living = _fmt(rec.income_cost_of_living)
            rec.jasper_income_ot_weekday = _fmt(rec.ot_total_weekday)
            rec.jasper_income_ot_holiday = _fmt(rec.ot_total_holiday)
            rec.jasper_income_ot_sunday = _fmt(rec.ot_total_sunday)
            rec.jasper_income_allowance = _fmt(rec.income_allowance)
            rec.jasper_income_food = _fmt(rec.income_food)
            rec.jasper_income_transport = _fmt(rec.income_transport)
            rec.jasper_income_trip = _fmt(rec.income_transport_trip)
            rec.jasper_income_commission = _fmt(rec.income_commission)
            rec.jasper_income_other = _fmt(rec.income_other)
            rec.jasper_total_income = _fmt(rec.total_gross)

    @api.depends('lateness_deduction', 'leave_deduction_total',
                 'deduction_absent', 'tax_monthly', 'sso_total',
                 'expense_provident', 'expense_ksl', 'expense_advance',
                 'expense_loan', 'expense_other', 'total_deduction')
    def _compute_jasper_deduction(self):
        for rec in self:
            rec.jasper_ded_late = _fmt(rec.lateness_deduction)
            rec.jasper_ded_leave = _fmt(rec.leave_deduction_total)
            rec.jasper_ded_absent = _fmt(rec.deduction_absent)
            rec.jasper_ded_tax = _fmt(rec.tax_monthly)
            rec.jasper_ded_sso = _fmt(rec.sso_total)
            rec.jasper_ded_provident = _fmt(rec.expense_provident)
            rec.jasper_ded_ksl = _fmt(rec.expense_ksl)
            rec.jasper_ded_advance = _fmt(rec.expense_advance)
            rec.jasper_ded_loan = _fmt(rec.expense_loan)
            rec.jasper_ded_other = _fmt(rec.expense_other)
            rec.jasper_total_deduction = _fmt(rec.total_deduction)

    @api.depends('accumulated_income', 'accumulated_vat',
                 'accumulated_social_security', 'net_salary')
    def _compute_jasper_summary(self):
        for rec in self:
            rec.jasper_accum_income = _fmt(rec.accumulated_income)
            rec.jasper_accum_tax = _fmt(rec.accumulated_vat)
            rec.jasper_accum_sso = _fmt(rec.accumulated_social_security)
            # ยอดสุทธิพิมพ์เสมอ แม้เป็นศูนย์ — ช่องว่างตรงนี้อ่านเป็น "ยังไม่คิด"
            rec.jasper_net_salary = '{:,.2f}'.format(rec.net_salary or 0.0)

    @api.depends('employee_id', 'company_id', 'month', 'year', 'payment_date')
    def _compute_jasper_header(self):
        for rec in self:
            employee = rec.employee_id
            company = rec.company_id or self.env.company
            rec.jasper_company_name = company.name or ''
            rec.jasper_company_address = rec._company_address_line()
            rec.jasper_company_logo = company.logo
            rec.jasper_employee_code = rec.employee_code or ''
            rec.jasper_employee_name = employee.full_name or ''
            rec.jasper_department = rec.department_id.name or ''
            rec.jasper_position = rec.position_id.name or ''
            rec.jasper_branch = rec.branch_id.name or ''
            rec.jasper_period_thai = '%s %s' % (
                THAI_MONTHS.get(int(rec.month or 0), ''), rec.year or '')
            rec.jasper_payment_date = _thai_date(rec.payment_date) or '-'
            rec.jasper_bank_account = employee.bank_account_number or ''
            rec.jasper_printed_by = self.env.user.name or ''


def _thai_date(value):
    if not value:
        return ''
    return '%d %s %d' % (value.day, THAI_MONTHS.get(value.month, ''),
                         value.year + 543)
