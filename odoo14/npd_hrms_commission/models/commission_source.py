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
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BRANCH_REPORT_MODEL = 'npd.commission.report'
SALES_REPORT_MODEL = 'npd.commission.report.sales'

# ช่วงย้ายระบบ: งวดสลิปที่ยังต้องไปเอาค่าคอมจากฝั่ง Odoo 14 (รูปแบบ 'YYYY-MM')
# ว่าง = ไม่ต้องไปเอา คิดจากข้อมูลฝั่ง 18 อย่างเดียว
O14_UNTIL_PARAM = 'npd.hrms.commission.o14_until'
O14_BRIDGE_MODEL = 'npd.commission.bridge'


class CommissionSource(models.AbstractModel):
    _name = 'commission.source'
    _description = 'ตัวอ่านยอดค่าคอมมิชชั่นจากรายงานฝั่ง ERP'

    # ------------------------------------------------------------------
    @api.model
    def _report_available(self, model_name):
        """โมดูลรายงานค่าคอมถูกติดตั้งแล้วหรือยัง"""
        return model_name in self.env

    # ------------------------------------------------------------------
    # ช่วงย้ายระบบ — ขอค่าคอมจากฝั่ง Odoo 14
    # ------------------------------------------------------------------
    # ค่าคอมจ่ายช้าหนึ่งเดือน สลิปเดือนแรกที่ทำบน Odoo 18 จึงต้องใช้ยอดขาย
    # ของเดือนก่อนหน้าซึ่งยังอยู่ฝั่ง 14 ทั้งก้อน (ยอดจริงอยู่ในฐาน ERP อีก
    # 4 ฐานที่ฝั่ง 18 ต่อไม่ถึงด้วย) งวดนั้นจึงขอตัวเลขสำเร็จรูปจากฝั่ง 14
    # ผ่าน XML-RPC แทนที่จะคิดเอง — สูตรฝั่ง 14 มีเงื่อนไขเยอะ (ขั้นบันได,
    # ยอดสาขาต้องเกินแสน, ยอดเซลล์ของสาขาเดียวกัน, บ้านเขียว, prorate คนลาออก)
    # ถ้าคิดใหม่อีกชุดสองระบบจะได้ตัวเลขไม่เท่ากันโดยไม่มีใครรู้

    @api.model
    def _o14_until(self):
        """งวดสลิปสุดท้ายที่ยังต้องไปเอาค่าคอมจากฝั่ง 14 — None = เลิกใช้แล้ว"""
        raw = (self.env['ir.config_parameter'].sudo()
               .get_param(O14_UNTIL_PARAM, default='') or '').strip()
        if not raw:
            return None
        try:
            year, month = raw.split('-')
            return int(year), int(month)
        except (ValueError, AttributeError):
            _logger.warning(
                '[COMMISSION] ค่า %s = %r ผิดรูปแบบ ต้องเป็น YYYY-MM',
                O14_UNTIL_PARAM, raw)
            return None

    @api.model
    def use_o14(self, month, year):
        """สลิปงวดนี้ต้องไปเอาค่าคอมจากฝั่ง 14 ไหม"""
        until = self._o14_until()
        if not until:
            return False
        try:
            return (int(year), int(month)) <= until
        except (TypeError, ValueError):
            return False

    @api.model
    def _o14_config(self):
        """การเชื่อมต่อฝั่ง 14 — คืน None ถ้ายังไม่ได้ติดตั้งโมดูลซิงก์"""
        if 'npd.hrms.sync.config' not in self.env:
            return None
        return self.env['npd.hrms.sync.config'].sudo().search(
            [('active', '=', True)], limit=1)

    @api.model
    def fetch_o14_commission(self, month, year, employee_codes=None):
        """ขอค่าคอมงวดนี้จากฝั่ง 14 — ถามครั้งเดียวต่อหนึ่ง transaction

        ฝั่ง 14 ต้องเปิด psycopg2 เข้าไปอ่านฐาน ERP อีก 4 ฐานต่อหนึ่งคำขอ
        ถ้าถามทีละคนตอนทำเงินเดือนร้อยกว่าใบจะช้ามาก จึงถามยกชุดแล้วเก็บ
        ผลไว้กับ cursor ซึ่งมีอายุเท่ากับรอบทำเงินเดือนหนึ่งรอบพอดี

        ต่อฝั่ง 14 ไม่ได้ให้ **หยุด** ไม่ใช่คืนศูนย์ — ค่าคอมเป็นเงินที่ต้อง
        จ่ายจริง ถ้าปล่อยเป็นศูนย์เงียบ ๆ พนักงานจะได้เงินขาดโดยไม่มีใครรู้
        """
        cache = getattr(self.env.cr, '_npd_o14_commission', None)
        if cache is None:
            cache = {}
            self.env.cr._npd_o14_commission = cache
        known = cache.setdefault((int(month), int(year)), {})

        wanted = {code for code in (employee_codes or []) if code}
        if wanted and wanted.issubset(set(known)):
            return known

        config = self._o14_config()
        if not config:
            raise UserError(
                'สลิปงวด %s/%s ตั้งไว้ให้ดึงค่าคอมจากฝั่ง Odoo 14 '
                'แต่ยังไม่ได้ตั้งค่าการเชื่อมต่อฝั่ง 14 '
                'ตั้งที่เมนูซิงก์ข้อมูลจาก Odoo 14 หรือล้างค่า %s '
                'ถ้าไม่ต้องใช้แล้ว' % (month, year, O14_UNTIL_PARAM))

        try:
            result = config.execute_kw(
                O14_BRIDGE_MODEL, 'get_commission_for_o18',
                [sorted(wanted) or False, int(month), int(year)])
        except Exception as error:
            raise UserError(
                'ขอค่าคอมงวด %s/%s จากฝั่ง Odoo 14 ไม่สำเร็จ (%s) '
                'ยังทำเงินเดือนงวดนี้ต่อไม่ได้ เพราะค่าคอมจะกลายเป็นศูนย์'
                % (month, year, error))

        for row in (result or {}).get('rows') or []:
            known[row.get('employee_code')] = row
        comm = (result or {}).get('commission_period') or {}
        _logger.info(
            '[COMMISSION] สลิปงวด %s/%s ดึงค่าคอมของเดือน %s/%s จากฝั่ง 14 '
            'ได้ %s คน รวม %.2f',
            month, year, comm.get('month'), comm.get('year'),
            (result or {}).get('count'), (result or {}).get('total') or 0.0)
        return known

    @api.model
    def get_o14_commission(self, employee, month, year):
        """ค่าคอมของพนักงานคนนี้จากฝั่ง 14 — รูปแบบเดียวกับตัวคิดฝั่ง 18"""
        known = self.fetch_o14_commission(
            month, year, [employee.employee_code])
        row = known.get(employee.employee_code) or {}
        if row.get('error'):
            _logger.warning('[COMMISSION] ฝั่ง 14 คำนวณ %s ไม่ผ่าน: %s',
                            employee.employee_code, row['error'])
        return {
            'branch_amount': row.get('income_commission') or 0.0,
            'sales_amount': row.get('income_commission_sale') or 0.0,
            'comm_type': row.get('comm_type') or 'sale_branch',
            'found': bool(row),
        }

    # ------------------------------------------------------------------
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
        """ยอดฐานคิดค่าคอมของสาขาในงวดนั้น = **ยอดเช่าสุทธิ**

        ต้องเป็นยอดสุทธิ (ยอดเช่า + รับชำระหนี้ − หนี้ค้าง − รายจ่าย)
        ไม่ใช่ยอดเช่าดิบ — ของ Odoo 14 ส่งตัวแปรชื่อ ``total_net_rental``
        เข้าไปคิดขั้นบันไดค่าคอม ถ้าใช้ยอดดิบ ค่าคอมจะสูงเกินจริงทุกสาขา
        เพราะยังไม่ได้หักรายจ่ายออก
        """
        Report = self.env[BRANCH_REPORT_MODEL].sudo()
        # โมดูลรายงานมีเมธอดสำเร็จให้ใช้ ใช้ตัวนั้นก่อนเสมอ
        if hasattr(Report, 'get_net_rental'):
            return Report.get_net_rental(branch, month, year, company=company)

        date_from, date_to = self._month_window(month, year)
        records = Report.search([
            ('branch_id', '=', branch.id),
            ('company_id', '=', company.id),
        ])
        field_names = Report._fields
        if 'month' in field_names and 'year' in field_names:
            records = records.filtered(
                lambda r: str(r.month) == str(month) and str(r.year) == str(year))
        elif 'date_from' in field_names:
            records = records.filtered(
                lambda r: r.date_from and date_from <= r.date_from <= date_to)
        for candidate in ('net_rental', 'total_amount', 'amount'):
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
        """ยอดฐานค่าคอม Sales = **ยอดเช่าสุทธิ** รวมทุกสาขาของเซลล์คนนั้น

        เหตุผลเดียวกับฝั่งสาขา — Odoo 14 ส่ง ``total_net_rental`` เข้าไปคิด
        ขั้นบันได ถ้าใช้ยอดเช่าดิบค่าคอมจะสูงเกินจริงเพราะยังไม่หักค่าขนส่ง
        และหนี้ค้าง
        """
        Report = self.env[SALES_REPORT_MODEL].sudo()
        if hasattr(Report, 'get_net_rental'):
            return Report.get_net_rental(employee, month, year, company=company)

        field_names = Report._fields
        domain = [('company_id', '=', company.id)]
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
        for candidate in ('net_rental', 'total_amount', 'amount'):
            if candidate in field_names:
                return sum(records.mapped(candidate))
        return 0.0
