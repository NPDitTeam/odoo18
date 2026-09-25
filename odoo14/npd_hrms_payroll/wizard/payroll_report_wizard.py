# -*- coding: utf-8 -*-
"""หน้าต่างเลือกงวดก่อนดูรายงานเงินเดือน

รายงานฝั่งเว็บเดิมให้เลือกบริษัท เดือน ปี แล้วค่อยกดดูหรือส่งออก ที่นี่ทำแบบ
เดียวกันเพื่อให้คนที่ใช้อยู่ทุกเดือนไม่ต้องเรียนรู้ใหม่ และไม่ต้องสร้างใบรายงาน
ทิ้งไว้ก่อนถึงจะดูได้

ตัวหน้าต่างไม่เก็บข้อมูลเอง แต่ไปสร้างหรือรีเฟรชใบรายงานของงวดนั้นให้อัตโนมัติ
งวดหนึ่งจึงมีใบเดียวเสมอ ไม่ว่าจะกดดูกี่ครั้ง และตัวเลขเป็นของล่าสุดจากสลิปจริง
"""
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

THAI_MONTH_SELECTION = [
    ('1', 'มกราคม'), ('2', 'กุมภาพันธ์'), ('3', 'มีนาคม'), ('4', 'เมษายน'),
    ('5', 'พฤษภาคม'), ('6', 'มิถุนายน'), ('7', 'กรกฎาคม'), ('8', 'สิงหาคม'),
    ('9', 'กันยายน'), ('10', 'ตุลาคม'), ('11', 'พฤศจิกายน'), ('12', 'ธันวาคม'),
]


class PayrollReportWizard(models.TransientModel):
    _name = 'payroll.report.wizard'
    _description = 'เลือกงวดรายงานเงินเดือน'

    company_id = fields.Many2one(
        'res.company', string='บริษัท',
        help='เว้นว่าง = ออกรายงานรวมทุกบริษัทที่มีสิทธิ์เห็น '
             'เหมือนตัวเลือก "ทุกบริษัท" ของรายงานเดิม')
    month = fields.Selection(THAI_MONTH_SELECTION, string='เดือน', required=True,
                             default=lambda self: str(fields.Date.context_today(self).month))
    year = fields.Selection(selection='_year_options', string='ปี', required=True,
                            default=lambda self: str(fields.Date.context_today(self).year))

    @api.model
    def _year_options(self):
        """ปีที่เลือกได้ — เอาเฉพาะปีที่มีสลิปจริง บวกปีปัจจุบันไว้เสมอ

        แสดงเป็น พ.ศ. ให้ตรงกับที่คนไทยใช้ แต่เก็บค่าเป็น ค.ศ. เหมือนในฐาน
        จะได้ไม่ต้องแปลงกลับไปมาแล้วพลาด
        """
        Slip = self.env['payroll.salary'].sudo()
        years = {row['year'] for row in Slip.search_read([], ['year']) if row.get('year')}
        years.add(str(fields.Date.context_today(self).year))
        options = []
        for year in sorted(years, reverse=True):
            try:
                options.append((year, str(int(year) + 543)))
            except (TypeError, ValueError):
                continue
        return options

    # ------------------------------------------------------------------
    def _prepare_report(self):
        """สร้างหรือรีเฟรชใบรายงานของงวดที่เลือก แล้วคืนใบนั้น"""
        self.ensure_one()
        companies = self.env['res.company'].sudo().search([]).ids
        Report = self.env['payroll.report'].sudo().with_context(
            allowed_company_ids=companies)

        domain = [('month', '=', int(self.month)), ('year', '=', self.year)]
        domain.append(('company_id', '=', self.company_id.id if self.company_id else False))
        report = Report.search(domain, limit=1)
        if not report:
            report = Report.create({
                'month': int(self.month),
                'year': self.year,
                'company_id': self.company_id.id if self.company_id else False,
            })
        report.action_refresh_lines()
        return report

    def action_view_report(self):
        """ดูรายงานในหน้าจอระบบ แบบเดียวกับรายงานภาษีฝั่ง Odoo 14

        ใช้หน้าจอของตัวเองแทนการเปิดแท็บใหม่ เพื่อให้ยังกดย้อนกลับไปเลือก
        งวดอื่นได้ทันทีโดยไม่หลุดออกจากระบบ
        """
        self.ensure_one()
        report = self._prepare_report()
        action = self.env.ref(
            'npd_hrms_payroll.action_payroll_report_backend').sudo().read()[0]
        action['context'] = {
            'active_id': report.id,
            'active_ids': report.ids,
            'active_model': 'payroll.report',
        }
        action['name'] = 'รายงานเงินเดือน %s %s' % (report.month_name, report.year_th)
        return action

    def action_export_excel(self):
        """ส่งออกไฟล์ Excel ของงวดที่เลือก"""
        self.ensure_one()
        report = self._prepare_report()
        return report.action_export_excel()

    def action_open_lines(self):
        """เปิดเป็นตารางในระบบ กรองและจัดกลุ่มต่อเองได้"""
        self.ensure_one()
        report = self._prepare_report()
        return report.action_open_lines()
