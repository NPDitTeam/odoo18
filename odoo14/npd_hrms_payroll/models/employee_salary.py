# -*- coding: utf-8 -*-
"""สิทธิพิเศษด้านเงินเดือนรายบุคคล

Odoo 14 ล็อกไว้ในโค้ดเป็น ``EXECUTIVE_TAX_CONFIG`` และ ``EXECUTIVE_EMPLOYEE_CODES``
คือฝังรหัสพนักงานของผู้บริหารไว้ใน payroll_salary.py ตรง ๆ
ทำให้ต้องแก้โค้ดและ deploy ใหม่ทุกครั้งที่เพิ่ม/เปลี่ยนคน และบริษัทที่เช่าระบบ
ไปใช้ก็ตั้งของตัวเองไม่ได้เลย

ย้ายมาเป็นฟิลด์บนบัตรพนักงาน — ฝ่ายบุคคลตั้งเองได้ มี tracking ว่าใครเปลี่ยนเมื่อไร
และมีช่องบันทึกเหตุผลไว้ให้ตรวจสอบย้อนหลัง
"""
from odoo import models, fields, api


class EmployeeSalaryPayroll(models.Model):
    _inherit = 'employee.salary'

    payroll_special_case = fields.Boolean(
        string='บุคคลพิเศษ (ตั้งกติกาเงินเดือนเฉพาะ)', default=False, tracking=True,
        groups='npd_hrms_base.group_hrms_payroll',
        help='เปิดเพื่อกำหนดวิธีคิดภาษี/ประกันสังคม/การหักสาย เฉพาะคนนี้')
    payroll_special_note = fields.Text(
        string='เหตุผลที่ตั้งเป็นบุคคลพิเศษ',
        groups='npd_hrms_base.group_hrms_payroll',
        help='บันทึกไว้ให้ผู้ตรวจสอบภายหลังเข้าใจว่าทำไมคนนี้คิดต่างจากคนอื่น')

    # ------------------------------------------------------------------
    # ภาษี
    # ------------------------------------------------------------------
    payroll_tax_mode = fields.Selection([
        ('auto', 'คำนวณตามปกติ'),
        ('fixed', 'ล็อกยอดคงที่ต่อเดือน'),
        ('exempt', 'ไม่หักภาษี'),
    ], string='วิธีคิดภาษี', default='auto', required=True, tracking=True,
        groups='npd_hrms_base.group_hrms_payroll')
    payroll_fixed_tax_amount = fields.Float(
        string='ภาษีคงที่ต่อเดือน', tracking=True,
        groups='npd_hrms_base.group_hrms_payroll')

    # ------------------------------------------------------------------
    # ประกันสังคม
    # ------------------------------------------------------------------
    payroll_sso_mode = fields.Selection([
        ('auto', 'คำนวณตามปกติ'),
        ('fixed', 'ล็อกยอดคงที่ต่อเดือน'),
        ('exempt', 'ไม่หักประกันสังคม'),
    ], string='วิธีคิดประกันสังคม', default='auto', required=True, tracking=True,
        groups='npd_hrms_base.group_hrms_payroll')
    payroll_fixed_sso_amount = fields.Float(
        string='ประกันสังคมคงที่ต่อเดือน', tracking=True,
        groups='npd_hrms_base.group_hrms_payroll')

    # ------------------------------------------------------------------
    # การหักสาย/ขาด/ลา และ OT
    # ------------------------------------------------------------------
    payroll_exempt_attendance = fields.Boolean(
        string='ไม่คิดสาย/ขาด/ลา', default=False, tracking=True,
        groups='npd_hrms_base.group_hrms_payroll',
        help='ใช้กับผู้บริหารหรือตำแหน่งที่ไม่ต้องลงเวลา')
    payroll_exempt_ot = fields.Boolean(
        string='ไม่คิดค่าล่วงเวลา', default=False, tracking=True,
        groups='npd_hrms_base.group_hrms_payroll')

    @api.onchange('payroll_special_case')
    def _onchange_payroll_special_case(self):
        """ปิดสวิตช์บุคคลพิเศษ → คืนทุกอย่างเป็นคำนวณตามปกติ

        กันเคสลืมล้างค่าแล้วยังมีภาษีคงที่ค้างอยู่โดยไม่มีใครเห็น
        """
        for rec in self:
            if not rec.payroll_special_case:
                rec.payroll_tax_mode = 'auto'
                rec.payroll_sso_mode = 'auto'
                rec.payroll_fixed_tax_amount = 0.0
                rec.payroll_fixed_sso_amount = 0.0
                rec.payroll_exempt_attendance = False
                rec.payroll_exempt_ot = False

    # ------------------------------------------------------------------
    # Helper ที่ payroll.salary เรียกใช้
    # ------------------------------------------------------------------
    def _payroll_tax_override(self):
        """(is_overridden, amount) — ภาษีที่ถูกล็อกไว้สำหรับคนนี้"""
        self.ensure_one()
        if not self.payroll_special_case:
            return False, 0.0
        if self.payroll_tax_mode == 'exempt':
            return True, 0.0
        if self.payroll_tax_mode == 'fixed':
            return True, self.payroll_fixed_tax_amount or 0.0
        return False, 0.0

    def _payroll_sso_override(self):
        """(is_overridden, amount) — ประกันสังคมที่ถูกล็อกไว้สำหรับคนนี้"""
        self.ensure_one()
        if not self.payroll_special_case:
            return False, 0.0
        if self.payroll_sso_mode == 'exempt':
            return True, 0.0
        if self.payroll_sso_mode == 'fixed':
            return True, self.payroll_fixed_sso_amount or 0.0
        return False, 0.0

    def _payroll_skips_attendance(self):
        self.ensure_one()
        return bool(self.payroll_special_case and self.payroll_exempt_attendance)

    def _payroll_skips_ot(self):
        self.ensure_one()
        return bool(self.payroll_special_case and self.payroll_exempt_ot)
