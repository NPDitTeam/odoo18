# -*- coding: utf-8 -*-
"""รายงานประกันสังคม — ไฟล์ .xlsx รูปแบบเดียวกับที่ยื่น สปส. (ตาม o14 npd_sso_report)

หนึ่งไฟล์ต่อบริษัท แยกชีตตามรหัสสาขา สปส. (000000, 200002, ...)
คอลัมน์: เลขบัตรประชาชน | คำนำหน้า | ชื่อ | สกุล | ค่าจ้าง | เงินสมทบ
"""
import base64
import io
import re
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP

from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.sso_config import DEFAULT_SSO_BRANCH

HEADERS = ['เลขบัตรประชาชน', 'คำนำหน้า', 'ชื่อ', 'สกุล', 'ค่าจ้าง', 'เงินสมทบ']
MONTHS_TH = ['', 'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
             'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']


def _baht(value):
    return int(Decimal(str(value or 0.0)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


class NpdSsoReportWizard(models.TransientModel):
    _name = 'npd.sso.report.wizard'
    _description = 'รายงานประกันสังคม'

    company_id = fields.Many2one('res.company', string='บริษัท', required=True,
                                 default=lambda self: self.env.company)
    year = fields.Char(string='ปี (ค.ศ.)', required=True,
                       default=lambda self: str(fields.Date.context_today(self).year))
    month = fields.Selection([(str(m), MONTHS_TH[m]) for m in range(1, 13)], string='เดือน',
                             required=True,
                             default=lambda self: str(fields.Date.context_today(self).month))
    preview = fields.Html(string='ตัวอย่าง', readonly=True, sanitize=False)
    file_data = fields.Binary(string='ไฟล์', readonly=True, attachment=False)
    file_name = fields.Char(string='ชื่อไฟล์', readonly=True)

    # ------------------------------------------------------------------
    def _config(self):
        return self.env['npd.sso.report.config'].search([('company_id', '=', self.company_id.id)], limit=1)

    @staticmethod
    def _is_foreign(emp):
        return (emp.nationality or '').strip() not in ('', 'ไทย')

    @classmethod
    def _id_value(cls, emp):
        """เลขที่ยื่น สปส.
        - คนไทย: เลขบัตรประชาชน (บางคนช่องเลขประกันสังคมไม่ตรงบัตร จึงไม่ยึดช่องนั้น)
        - ต่างชาติ: เลขประกันสังคมที่ สปส. ออกให้ก่อน (ช่องเลขบัตรมักเป็นบัตรชมพู 6666…)"""
        order = ((emp.social_security_number, emp.id_card_number, emp.passport_number)
                 if cls._is_foreign(emp) else
                 (emp.id_card_number, emp.social_security_number, emp.passport_number))
        for raw in order:
            digits = re.sub(r'\D', '', raw or '')
            if digits:
                return digits
        return ''

    @staticmethod
    def _sso_wage(pay):
        """ค่าจ้างที่ยื่น สปส. = เงินเดือน (ตามวันที่ทำงานจริง) + เงินเพิ่มประจำ"""
        return (pay._prorated_salary()
                + (pay.income_cost_of_living or 0.0)
                + (pay.income_position_allowance or 0.0)
                + (pay.income_experience_allowance or 0.0)
                + (pay.income_professional_allowance or 0.0))

    def _collect(self):
        """{รหัสสาขา: [แถว]}, คำเตือน — เฉพาะสลิปเดือนนั้นที่มียอดประกันสังคม"""
        self.ensure_one()
        config = self._config()
        if not config:
            raise UserError(_('ยังไม่ได้กำหนดค่ารายงานประกันสังคมของ %s '
                              '(เมนู กำหนดค่ารายงานประกันสังคม หรือรันซิงก์ HR จาก o14)')
                            % self.company_id.name)
        # นับเฉพาะเดือนที่มีรอบทำเงินเดือน (ไม่ใช่ร่าง/ยกเลิก) เหมือน o14
        # รอบที่ยกจาก o14 เป็นของทั้งเครือแต่ผูกได้บริษัทเดียว จึงไม่เทียบบริษัทของรอบ
        if not self.env['payroll.period'].sudo().search_count([
                ('year', '=', int(self.year)),
                ('month', '=', int(self.month)), ('state', 'not in', ('draft', 'cancelled'))]):
            raise UserError(_('%s เดือน %s/%s ยังไม่มีรอบทำเงินเดือน')
                            % (self.company_id.name, self.month, self.year))
        # บริษัท = บริษัทที่จ่ายในเดือนนั้น (แถว ภ.ง.ด.1) ไม่มีค่อยใช้บริษัทของสลิป
        # สลิปที่ยกจาก o14 ใช้สังกัดปัจจุบันของพนักงาน ซึ่งผิดสำหรับคนที่ย้ายบริษัทภายหลัง
        payrolls = self.env['payroll.salary'].sudo().search([
            ('year', '=', self.year), ('month', '=', int(self.month)), ('sso_total', '>', 0)])
        paid_by = {l.payroll_id.id: l.company_id for l in self.env['pnd1.line'].sudo().search([
            ('payroll_id', 'in', payrolls.ids), ('source_type', '=', 'system')])}
        payrolls = payrolls.filtered(
            lambda p: (paid_by.get(p.id) or p.company_id) == self.company_id)
        sheets, warnings = {}, []
        for pay in payrolls.sorted(lambda p: (p.employee_id.firstname or '', p.id)):
            emp = pay.employee_id
            code = config.sso_branch_code_for(emp.branch_id)
            wage = self._sso_wage(pay) if config.wage_source == 'salary' else pay.total_gross
            idv = self._id_value(emp)
            if not idv:
                warnings.append(_('%s %s ไม่มีเลขบัตรประชาชน/เลขประกันสังคม') % (
                    emp.employee_code or '', emp.firstname or ''))
            elif self._is_foreign(emp) and not re.sub(r'\D', '', emp.social_security_number or ''):
                warnings.append(_('%s %s (ต่างชาติ) ยังไม่ได้กรอกเลขประกันสังคม ใช้เลข %s แทน — ตรวจก่อนยื่น') % (
                    emp.employee_code or '', emp.firstname or '', idv))
            sheets.setdefault(code, []).append({
                'id': idv,
                'prefix': emp.prefix_th or '',
                'firstname': (emp.firstname or '').strip(),
                'lastname': (emp.lastname or '').strip(),
                'wage': _baht(wage),
                'contribution': _baht(pay.sso_total),
                'branch': emp.branch_id.name or '-',
            })
        ordered = OrderedDict()
        for code in sorted(sheets, key=lambda c: (c != DEFAULT_SSO_BRANCH, c)):
            ordered[code] = sheets[code]
        return config, ordered, warnings

    def _file_name(self, config):
        be_year = int(self.year) + 543
        prefix = config.employer_account or 'สปส'
        return '%s_%d%02d_%s.xlsx' % (prefix, be_year, int(self.month), self.company_id.name)

    # ------------------------------------------------------------------
    def action_preview(self):
        self.ensure_one()
        config, sheets, warnings = self._collect()
        rows = Markup('')
        total_n = total_w = total_c = 0
        for code, lines in sheets.items():
            branches = sorted({l['branch'] for l in lines})
            w = sum(l['wage'] for l in lines)
            c = sum(l['contribution'] for l in lines)
            total_n += len(lines)
            total_w += w
            total_c += c
            rows += Markup('<tr><td>%s</td><td>%s</td><td style="text-align:right">%s</td>'
                           '<td style="text-align:right">%s</td><td style="text-align:right">%s</td></tr>') % (
                code, ', '.join(branches), len(lines), '{:,}'.format(w), '{:,}'.format(c))
        html = Markup('<p><b>%s</b></p>') % (_('%s เดือน %s %s — %s คน ค่าจ้างรวม %s เงินสมทบรวม %s บาท') % (
            self.company_id.name, MONTHS_TH[int(self.month)], int(self.year) + 543, total_n,
            '{:,}'.format(total_w), '{:,}'.format(total_c)))
        if not sheets:
            html += Markup('<p>%s</p>') % _('ไม่พบสลิปที่มียอดประกันสังคมในเดือนนี้')
        else:
            html += Markup('<table class="table table-sm"><thead><tr><th>รหัสสาขา สปส.</th>'
                           '<th>สาขาของเรา</th><th>คน</th><th>ค่าจ้าง</th><th>เงินสมทบ</th>'
                           '</tr></thead><tbody>') + rows + Markup('</tbody></table>')
        if not config.employer_account:
            warnings.insert(0, _('ยังไม่ได้ใส่เลขที่บัญชีนายจ้าง ชื่อไฟล์จะขึ้นต้นด้วย "สปส"'))
        if warnings:
            html += Markup('<div class="alert alert-warning"><ul>%s</ul></div>') % Markup('').join(
                Markup('<li>%s</li>') % escape(w) for w in warnings)
        self.write({'preview': html, 'file_data': False, 'file_name': False})
        return self._reopen()

    def action_export(self):
        self.ensure_one()
        import xlsxwriter
        config, sheets, _warnings = self._collect()
        if not sheets:
            raise UserError(_('ไม่พบสลิปที่มียอดประกันสังคมในเดือนนี้'))
        buf = io.BytesIO()
        book = xlsxwriter.Workbook(buf, {'in_memory': True})
        head = book.add_format({'bold': True, 'align': 'center'})
        id_fmt = book.add_format({'num_format': '0000000000000'})
        num_fmt = book.add_format({'num_format': '0'})
        for code, lines in sheets.items():
            sheet = book.add_worksheet(code)
            for col, title in enumerate(HEADERS):
                sheet.write(0, col, title, head)
            for r, line in enumerate(lines, start=1):
                if line['id'].isdigit():
                    sheet.write_number(r, 0, int(line['id']), id_fmt)
                else:
                    sheet.write_string(r, 0, line['id'])
                sheet.write_string(r, 1, line['prefix'])
                sheet.write_string(r, 2, line['firstname'])
                sheet.write_string(r, 3, line['lastname'])
                sheet.write_number(r, 4, line['wage'], num_fmt)
                sheet.write_number(r, 5, line['contribution'], num_fmt)
            for col, width in enumerate((16, 10, 18, 18, 10, 10)):
                sheet.set_column(col, col, width)
        book.close()
        self.write({'file_data': base64.b64encode(buf.getvalue()), 'file_name': self._file_name(config)})
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'new', 'name': _('รายงานประกันสังคม'),
        }
