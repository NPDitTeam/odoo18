# -*- coding: utf-8 -*-
"""ตัวอ่านยอดค่าคอมมิชชั่นจากฝั่ง ERP

**นี่คือจุดที่เปลี่ยนไปมากที่สุดจาก Odoo 14**

เดิม: HR อยู่คนละฐานกับ ERP (แยก DB ต่อบริษัท) โมดูล ``cross_db_commission``
จึงต้องเปิด psycopg2 ต่อตรงเข้าไปอีก 4 ฐาน (NPD_Intertrading_New,
NPD_S_Group_New_V2, NPD_Bangkok_New, NPD_Steeltech_New) แล้วยิง SQL ดิบ
~840 บรรทัด พร้อมต้อง push รายชื่อ Sales สำนักงานใหญ่ + snapshot เงินเดือน
ข้ามฐานกลับไปด้วย

ตอนนี้: Odoo 18 ใช้ฐานเดียวหลายบริษัท → อ่านผ่าน ORM ตรง ๆ
ไม่มี psycopg2 ไม่มี SQL ดิบ ไม่มี credential ฝังในโค้ด และไม่ต้อง push อะไรกลับ

โมดูลต้นทาง ``npd_commission_report`` (``npd.commission.report`` /
``npd.commission.report.sales``) **ยังไม่ถูกพอร์ตมา Odoo 18**
โค้ดนี้จึงตรวจก่อนเสมอว่ามีโมเดลนั้นหรือยัง ถ้ายังไม่มีจะคืน 0
และเขียน log บอก แทนที่จะ error — ทำให้เงินเดือนส่วนอื่นยังทำงานได้ตามปกติ
"""
import calendar
import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import models, api

_logger = logging.getLogger(__name__)

BRANCH_REPORT_MODEL = 'npd.commission.report'
SALES_REPORT_MODEL = 'npd.commission.report.sales'


class CommissionSource(models.AbstractModel):
    _name = 'commission.source'
    _description = 'ตัวอ่านยอดค่าคอมมิชชั่นจากรายงานฝั่ง ERP'

    # ------------------------------------------------------------------
    @api.model
    def _report_available(self, model_name):
        """โมดูลรายงานค่าคอมถูกติดตั้งแล้วหรือยัง"""
        return model_name in self.env

    @api.model
    def get_commission_period(self, month, year):
        """งวดค่าคอมของสลิปเดือนนี้ = เดือนก่อนหน้า

        ค่าคอมจ่ายเดือนถัดไปเสมอ (ปิดยอดเดือน N แล้วจ่ายในเดือน N+1)
        เดือน 1 → ธันวาคมปีก่อน
        """
        target = date(int(year), int(month), 1) - relativedelta(months=1)
        return target.month, target.year

    @api.model
    def _month_window(self, month, year):
        last_day = calendar.monthrange(int(year), int(month))[1]
        return (date(int(year), int(month), 1),
                date(int(year), int(month), last_day))

    # ------------------------------------------------------------------
    # ค่าคอมสาขา
    # ------------------------------------------------------------------
    @api.model
    def get_branch_commission(self, employee, month, year):
        """ค่าคอมสาขาที่พนักงานคนนี้ได้รับ

        สูตร: ยอดฐานของสาขา × อัตราค่าคอมสาขา × (สัดส่วนของคนนี้ ÷ สัดส่วนรวมสาขา)
        """
        result = {'amount': 0.0, 'base': 0.0, 'rate': 0.0,
                  'ratio': 0.0, 'total_ratio': 0.0, 'available': False}
        branch = employee.branch_id
        if not branch:
            return result
        if not self._report_available(BRANCH_REPORT_MODEL):
            _logger.info(
                '[COMMISSION] ยังไม่ได้ติดตั้งโมดูล npd_commission_report '
                '→ ค่าคอมสาขาของ %s = 0', employee.employee_code)
            return result

        result['available'] = True
        comm_month, comm_year = self.get_commission_period(month, year)
        company = employee.company_id or self.env.company

        base = self._sum_branch_base(branch, comm_month, comm_year, company)
        if not base:
            return result

        Config = self.env['commission.rate.branch.sales']
        branch_rate, _sales_rate = Config.get_rates('sale_branch', company)
        BranchConfig = self.env['commission.branch.config']
        ratio = BranchConfig.get_ratio_for_employee(branch, employee)
        total_ratio = BranchConfig.get_total_ratio_for_branch(branch)

        result.update({'base': base, 'rate': branch_rate,
                       'ratio': ratio, 'total_ratio': total_ratio})
        if not total_ratio or not ratio:
            return result
        pool = base * (branch_rate / 100.0)
        result['amount'] = pool * (ratio / total_ratio)
        return result

    @api.model
    def _sum_branch_base(self, branch, month, year, company):
        """ยอดฐานคิดค่าคอมของสาขาในงวดนั้น

        แยกเป็นเมธอดต่างหากเพื่อให้ปรับวิธีอ่านได้ที่เดียว เมื่อพอร์ต
        ``npd_commission_report`` มาแล้วชื่อฟิลด์อาจต่างจากที่คาดไว้
        """
        Report = self.env[BRANCH_REPORT_MODEL].sudo()
        date_from, date_to = self._month_window(month, year)
        records = Report.search([
            ('branch_id', '=', branch.id),
            ('company_id', '=', company.id),
        ])
        # รองรับได้ทั้งแบบเก็บ month/year และแบบเก็บช่วงวันที่
        field_names = Report._fields
        if 'month' in field_names and 'year' in field_names:
            records = records.filtered(
                lambda r: str(r.month) == str(month) and str(r.year) == str(year))
        elif 'date_from' in field_names:
            records = records.filtered(
                lambda r: r.date_from and date_from <= r.date_from <= date_to)
        for candidate in ('rental_amount', 'total_amount', 'amount_untaxed', 'amount'):
            if candidate in field_names:
                return sum(records.mapped(candidate))
        _logger.warning(
            '[COMMISSION] ไม่พบฟิลด์ยอดฐานบน %s — ตรวจชื่อฟิลด์หลังพอร์ตโมดูลรายงาน',
            BRANCH_REPORT_MODEL)
        return 0.0

    # ------------------------------------------------------------------
    # ค่าคอม Sales
    # ------------------------------------------------------------------
    @api.model
    def get_sales_commission(self, employee, month, year):
        """ค่าคอม Sales ของพนักงานคนนี้

        แยกสองประเภทตามที่พนักงานอยู่ในรายชื่อ Sales สำนักงานใหญ่หรือไม่
        เพราะอัตราและขั้นยอดต่างกัน
        """
        result = {'amount': 0.0, 'base': 0.0, 'rate': 0.0,
                  'comm_type': 'sale_branch', 'available': False}
        company = employee.company_id or self.env.company

        # หาประเภทก่อนตรวจว่ามีรายงานไหม — ประเภทมาจากรายชื่อฝั่ง HR ล้วน ๆ
        # ผู้เรียกจึงยังรู้ว่าคนนี้คิดแบบสาขาหรือสำนักงานใหญ่ แม้ยอดจะยังเป็น 0
        comm_type = (
            'sale_headoffice'
            if self.env['commission.sale.headoffice'].is_headoffice_employee(employee)
            else 'sale_branch')
        result['comm_type'] = comm_type

        if not self._report_available(SALES_REPORT_MODEL):
            _logger.info(
                '[COMMISSION] ยังไม่ได้ติดตั้งโมดูล npd_commission_report '
                '→ ค่าคอม Sales ของ %s = 0', employee.employee_code)
            return result

        result['available'] = True
        comm_month, comm_year = self.get_commission_period(month, year)
        base = self._sum_sales_base(employee, comm_month, comm_year, company)
        if not base:
            return result

        rate = self.env['commission.rate.config'].get_rate_for_amount(
            base, comm_type, company)
        result.update({'base': base, 'rate': rate,
                       'amount': base * (rate / 100.0)})
        return result

    @api.model
    def _sum_sales_base(self, employee, month, year, company):
        Report = self.env[SALES_REPORT_MODEL].sudo()
        field_names = Report._fields
        domain = [('company_id', '=', company.id)]
        # จับคู่พนักงานกับ Sales ด้วยรหัสพนักงานก่อน แล้วค่อยชื่อ
        if 'employee_code' in field_names:
            domain.append(('employee_code', '=', employee.employee_code))
        elif 'sales_name' in field_names:
            domain.append(('sales_name', '=', employee.full_name))
        else:
            _logger.warning(
                '[COMMISSION] ไม่พบฟิลด์จับคู่พนักงานบน %s', SALES_REPORT_MODEL)
            return 0.0

        records = Report.search(domain)
        if 'month' in field_names and 'year' in field_names:
            records = records.filtered(
                lambda r: str(r.month) == str(month) and str(r.year) == str(year))
        for candidate in ('total_amount', 'rental_amount', 'amount_untaxed', 'amount'):
            if candidate in field_names:
                return sum(records.mapped(candidate))
        return 0.0
