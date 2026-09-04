# -*- coding: utf-8 -*-
"""ออกหนังสือรับรองหักภาษี ณ ที่จ่าย ให้พนักงานทั้งปีในครั้งเดียว

ปลายปีต้องออกให้พนักงานทุกคน การกดสร้างทีละใบไม่ไหว วิซาร์ดนี้จึงไล่จาก
สลิปเงินเดือนของปีนั้นว่ามีใครบ้าง แล้วสร้าง/อัปเดตให้ครบ

รันซ้ำได้ — ใบที่มีอยู่แล้วจะถูกคำนวณใหม่แทนการสร้างซ้ำ (มี unique
ต่อพนักงานต่อปีอยู่แล้ว) เพราะระหว่างปียอด ภ.ง.ด.1 ยังเปลี่ยนได้
"""
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GenerateHRWTCert(models.TransientModel):
    _name = 'generate.hr.wt.cert'
    _description = 'ออกหนังสือรับรองหักภาษี ณ ที่จ่ายทั้งปี'

    year = fields.Char(
        string='ปีภาษี', required=True,
        default=lambda self: str(fields.Date.today().year),
        help='ค้นหาพนักงานที่มีสลิปเงินเดือนในปีนี้ — ใส่ ค.ศ. หรือ พ.ศ. ก็ได้')
    company_id = fields.Many2one(
        'res.company', string='บริษัท',
        default=lambda self: self.env.company,
        help='ออกให้เฉพาะพนักงานของบริษัทนี้ — เว้นว่างคือทุกบริษัทที่เข้าถึงได้')

    def action_generate_all(self):
        self.ensure_one()
        Cert = self.env['hr.withholding.tax.cert']
        year = (self.year or '').strip()
        try:
            y = int(year)
        except (TypeError, ValueError):
            raise UserError(_('ปีภาษีต้องเป็นตัวเลข'))
        y = y - 543 if y >= 2500 else y

        domain = [('year', 'in', [str(y), str(y + 543)])]
        if self.company_id:
            domain.append(('employee_id.company_id', '=', self.company_id.id))
        payrolls = self.env['payroll.salary'].search(domain)
        if not payrolls:
            raise UserError(_('ไม่พบข้อมูลเงินเดือนในปี %s') % year)

        created = updated = skipped = 0
        for employee in payrolls.mapped('employee_id'):
            existing = Cert.search([
                ('employee_id', '=', employee.id),
                ('report_year', '=', year),
            ], limit=1)

            cert = existing or Cert.new({
                'employee_id': employee.id, 'report_year': year})
            income, tax = cert._income_and_tax()
            if not income:
                # ไม่มียอดทั้งปี = ออกเอกสารเปล่าไปก็ไม่มีประโยชน์
                skipped += 1
                continue
            sso, provident = cert._fund_totals()
            line_vals = {
                'wt_cert_income_type': '1',
                'wt_cert_income_desc':
                    'เงินเดือน ค่าจ้าง เบี้ยเลี้ยง โบนัส ฯลฯ 40(1)',
                'base': income,
                'wt_percent': (tax / income * 100) if income else 0.0,
                'amount': tax,
            }

            if existing:
                # ยืนยันไปแล้วต้องกลับเป็นร่างก่อน ไม่งั้นแก้ยอดไม่ได้
                if existing.state != 'draft':
                    existing.write({'state': 'draft'})
                existing.wt_line.unlink()
                existing.write({
                    'wt_line': [(0, 0, line_vals)],
                    'sso_amount': sso,
                    'provident_fund_amount': provident,
                    'state': 'done',
                })
                updated += 1
            else:
                Cert.create({
                    'employee_id': employee.id,
                    'report_year': year,
                    'income_tax_form': 'pnd1',
                    'tax_payer': 'withholding',
                    'sso_amount': sso,
                    'provident_fund_amount': provident,
                    'wt_line': [(0, 0, line_vals)],
                }).write({'state': 'done'})
                created += 1

        _logger.info('[50 ทวิ] ปี %s สร้างใหม่ %d อัปเดต %d ข้าม %d',
                     year, created, updated, skipped)
        action = self.env['ir.actions.actions']._for_xml_id(
            'npd_hr_wt_cert.action_hr_withholding_tax_cert')
        action['domain'] = [('report_year', '=', year)]
        action['context'] = {'default_report_year': year}
        return action
