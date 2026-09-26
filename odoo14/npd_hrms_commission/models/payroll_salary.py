# -*- coding: utf-8 -*-
"""ต่อค่าคอมมิชชั่นเข้าสลิปเงินเดือน

แยกเป็นโมดูลต่างหากเพราะค่าคอมพึ่งข้อมูลจากฝั่ง ERP — ถ้าบริษัทที่เช่าระบบ
ใช้แค่งานบุคคล ไม่ต้องติดตั้งโมดูลนี้ เงินเดือนก็ทำงานได้ครบ
"""
import logging

from odoo import models, fields, api

from .commission_source import BRANCH_REPORT_MODEL, SALES_REPORT_MODEL

_logger = logging.getLogger(__name__)


class PayrollSalaryCommission(models.Model):
    _inherit = 'payroll.salary'

    commission_branch_base = fields.Float(
        string='ยอดฐานค่าคอมสาขา', readonly=True)
    commission_branch_rate = fields.Float(
        string='อัตราค่าคอมสาขา (%)', readonly=True)
    commission_branch_sales_base = fields.Float(
        string='ยอดฐานเซลล์ในสาขา', readonly=True,
        help='ยอดสุทธิของเซลล์ที่ขายในสาขานี้ — รวมเข้ากองเดียวกับค่าคอมสาขา '
             'แล้วแบ่งกันตามสัดส่วน คนละตัวกับค่าคอม Sales รายบุคคล')
    commission_branch_sales_rate = fields.Float(
        string='อัตราเซลล์ในสาขา (%)', readonly=True)
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
        compute='_compute_commission_source_ready',
        help='ปิดอยู่ = ยังไม่ได้ติดตั้งโมดูลรายงานค่าคอมฝั่ง ERP '
             '(npd_commission_report) ระบบจึงคิดค่าคอมเป็น 0')

    def _compute_commission_source_ready(self):
        """ดูจากของจริงตอนเปิดหน้าจอ ไม่ใช่ค่าที่ค้างไว้ตอนคำนวณสลิป

        เดิมฟิลด์นี้เก็บค่าลงฐานตอนคำนวณสลิปครั้งล่าสุด พอติดตั้งโมดูลรายงาน
        ทีหลัง สลิปที่คำนวณไว้ก่อนหน้าจะยังค้างว่า "ยังไม่มีโมดูล" และขึ้น
        คำเตือนต่อไปเรื่อย ๆ ทั้งที่ติดตั้งไปแล้ว ต้องไปกดคำนวณใหม่ทีละใบ
        ถึงจะหาย — คิดสดทุกครั้งจึงตรงกับความจริงเสมอ
        """
        Source = self.env['commission.source']
        ready = (Source._report_available(BRANCH_REPORT_MODEL)
                 or Source._report_available(SALES_REPORT_MODEL))
        for rec in self:
            rec.commission_source_ready = ready

    commission_from_o14 = fields.Boolean(
        string='ค่าคอมมาจาก Odoo 14', readonly=True,
        help='งวดช่วงย้ายระบบ — ยอดขายของเดือนก่อนยังอยู่ฝั่ง Odoo 14 '
             'ระบบจึงขอตัวเลขค่าคอมสำเร็จรูปจากฝั่งนั้นมาแทนการคิดเอง')

    manual_override_commission = fields.Boolean(
        string='กรอกค่าคอมเอง', default=False,
        help='ติ๊กแล้วระบบจะไม่ดึงค่าคอมมาทับ ใช้ตอนตกลงยอดกันเป็นกรณีพิเศษ')

    def _recalculate(self):
        """ดึงค่าคอมก่อน แล้วค่อยให้เอนจินหลักคำนวณต่อ

        ต้องมาก่อนเพราะค่าคอมเป็นส่วนหนึ่งของฐานภาษี (รายได้ประจำ)
        """
        todo = self.filtered(
            lambda r: not r.manual_override and not r.manual_override_commission)
        todo._prefetch_o14_commission()
        for rec in todo:
            rec._fetch_commission()
        return super()._recalculate()

    def _prefetch_o14_commission(self):
        """ถามฝั่ง 14 ครั้งเดียวต่อหนึ่งงวด ไม่ใช่ทีละใบ

        ฝั่ง 14 ต้องเปิดต่อเข้าไปอ่านฐาน ERP อีกสี่ฐานต่อหนึ่งคำขอ
        ทำเงินเดือนร้อยกว่าใบแล้วถามทีละใบคือรอเป็นสิบนาที
        """
        Source = self.env['commission.source']
        periods = {}
        for rec in self:
            if not rec.employee_id or not rec.month or not rec.year:
                continue
            if not Source.use_o14(rec.month, rec.year):
                continue
            periods.setdefault((rec.month, rec.year), set()).add(
                rec.employee_code)
        for (month, year), codes in periods.items():
            Source.fetch_o14_commission(month, year, sorted(codes))

    def _fetch_commission(self):
        self.ensure_one()
        if not self.employee_id or not self.month or not self.year:
            return
        Source = self.env['commission.source']

        if Source.use_o14(self.month, self.year):
            self._fetch_commission_from_o14(Source)
            return

        branch = Source.get_branch_commission(self.employee_id, self.month, self.year)
        sales = Source.get_sales_commission(self.employee_id, self.month, self.year)

        self.income_commission = branch['amount']
        self.commission_branch_base = branch['base']
        self.commission_branch_rate = branch['rate']
        self.commission_branch_ratio = branch['ratio']
        self.commission_branch_total_ratio = branch['total_ratio']
        self.commission_branch_sales_base = branch['sales_in_branch_base']
        self.commission_branch_sales_rate = branch['sales_in_branch_rate']

        self.income_commission_sale = sales['amount']
        self.commission_sale_base = sales['base']
        self.commission_sale_rate = sales['rate']
        self.commission_sale_type = sales['comm_type']
        self.commission_from_o14 = False

        if self.income_commission or self.income_commission_sale:
            _logger.info(
                '[COMMISSION] emp=%s งวด=%s/%s สาขา=%.2f Sales=%.2f',
                self.employee_code, self.month, self.year,
                self.income_commission, self.income_commission_sale)

    def _fetch_commission_from_o14(self, Source):
        """งวดช่วงย้ายระบบ — ยอดที่ฝั่ง 14 คิดเสร็จแล้ว เอามาลงตรง ๆ

        ไม่มียอดฐานกับอัตรามาด้วย เพราะฝั่ง 14 ไม่ได้เก็บไว้ที่สลิป
        (เขียนลง log ตอนคำนวณอย่างเดียว) ช่องยอดฐาน/อัตราจึงว่างไว้
        แล้วติดธง "ค่าคอมมาจาก Odoo 14" บอกคนอ่านสลิปแทน
        """
        self.ensure_one()
        data = Source.get_o14_commission(self.employee_id, self.month, self.year)

        self.income_commission = data['branch_amount']
        self.income_commission_sale = data['sales_amount']
        self.commission_sale_type = data['comm_type']
        self.commission_branch_base = 0.0
        self.commission_branch_rate = 0.0
        self.commission_branch_ratio = 0.0
        self.commission_branch_total_ratio = 0.0
        self.commission_branch_sales_base = 0.0
        self.commission_branch_sales_rate = 0.0
        self.commission_sale_base = 0.0
        self.commission_sale_rate = 0.0
        self.commission_from_o14 = True

        if not data['found']:
            _logger.warning(
                '[COMMISSION] ฝั่ง 14 ไม่มีข้อมูลพนักงาน %s งวด %s/%s',
                self.employee_code, self.month, self.year)
