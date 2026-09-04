# -*- coding: utf-8 -*-
"""ต่อค่าคอมมิชชั่นเข้าสลิปเงินเดือน

แยกเป็นโมดูลต่างหากเพราะค่าคอมพึ่งข้อมูลจากฝั่ง ERP — ถ้าบริษัทที่เช่าระบบ
ใช้แค่งานบุคคล ไม่ต้องติดตั้งโมดูลนี้ เงินเดือนก็ทำงานได้ครบ
"""
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class PayrollSalaryCommission(models.Model):
    _inherit = 'payroll.salary'

    commission_branch_base = fields.Float(
        string='ยอดฐานค่าคอมสาขา', readonly=True)
    commission_branch_rate = fields.Float(
        string='อัตราค่าคอมสาขา (%)', readonly=True)
    commission_branch_ratio = fields.Float(
        string='สัดส่วนของพนักงาน', readonly=True)
    commission_branch_total_ratio = fields.Float(
        string='สัดส่วนรวมทั้งสาขา', readonly=True)

    commission_sale_base = fields.Float(
        string='ยอดฐานค่าคอม Sales', readonly=True)
    commission_sale_rate = fields.Float(
        string='อัตราค่าคอม Sales (%)', readonly=True)
    commission_sale_type = fields.Selection([
        ('sale_branch', 'ค่าคอม Sale สาขา'),
        ('sale_headoffice', 'ค่าคอม Sale สำนักงานใหญ่'),
    ], string='ประเภทค่าคอม Sales', readonly=True)

    commission_source_ready = fields.Boolean(
        string='มีข้อมูลรายงานค่าคอมแล้ว', readonly=True,
        help='ปิดอยู่ = ยังไม่ได้ติดตั้งโมดูลรายงานค่าคอมฝั่ง ERP '
             '(npd_commission_report) ระบบจึงคิดค่าคอมเป็น 0')

    manual_override_commission = fields.Boolean(
        string='กรอกค่าคอมเอง', default=False,
        help='ติ๊กแล้วระบบจะไม่ดึงค่าคอมมาทับ ใช้ตอนตกลงยอดกันเป็นกรณีพิเศษ')

    def _recalculate(self):
        """ดึงค่าคอมก่อน แล้วค่อยให้เอนจินหลักคำนวณต่อ

        ต้องมาก่อนเพราะค่าคอมเป็นส่วนหนึ่งของฐานภาษี (รายได้ประจำ)
        """
        for rec in self:
            if not rec.manual_override and not rec.manual_override_commission:
                rec._fetch_commission()
        return super()._recalculate()

    def _fetch_commission(self):
        self.ensure_one()
        if not self.employee_id or not self.month or not self.year:
            return
        Source = self.env['commission.source']

        branch = Source.get_branch_commission(self.employee_id, self.month, self.year)
        sales = Source.get_sales_commission(self.employee_id, self.month, self.year)

        self.income_commission = branch['amount']
        self.commission_branch_base = branch['base']
        self.commission_branch_rate = branch['rate']
        self.commission_branch_ratio = branch['ratio']
        self.commission_branch_total_ratio = branch['total_ratio']

        self.income_commission_sale = sales['amount']
        self.commission_sale_base = sales['base']
        self.commission_sale_rate = sales['rate']
        self.commission_sale_type = sales['comm_type']

        self.commission_source_ready = branch['available'] or sales['available']

        if self.income_commission or self.income_commission_sale:
            _logger.info(
                '[COMMISSION] emp=%s งวด=%s/%s สาขา=%.2f Sales=%.2f',
                self.employee_code, self.month, self.year,
                self.income_commission, self.income_commission_sale)
