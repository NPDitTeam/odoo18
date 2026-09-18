# -*- coding: utf-8 -*-
"""รายงานหักเงินสงเคราะห์ลูกจ้าง — ไฟล์ Excel ส่งกองทุนสงเคราะห์ลูกจ้าง แยกตามสังกัด

พอร์ตจาก Odoo 14 (employee_salary/models/welfare_fund_report.py) ต่างกันตรงที่
"สังกัด" ของ Odoo 18 คือ res.company จริง ๆ ไม่ใช่ Selection ของชื่อบริษัท

รูปแบบไฟล์ยึดตามแบบฟอร์มของกองทุน (WfcsFormTemplate) หัวกระดาษ 3 บรรทัด
แล้วตามด้วยตาราง 11 คอลัมน์ — ห้ามเพิ่ม/สลับคอลัมน์ เพราะระบบของกองทุนอ่านตามตำแหน่ง

รายงานสร้างให้อัตโนมัติเมื่อคำนวณรอบเงินเดือนใหม่และตอนอนุมัติรอบ โดยดูจากยอด
ที่ถูกหักจริงในรอบนั้น ซึ่งมาจากเมนู "หักเงินสงเคราะห์ลูกจ้าง"
(เดือนที่เริ่มหักจึงมาจากการตั้งค่าที่เมนูนั้น ไม่ได้ตั้งซ้ำที่นี่)
"""
import base64
import io
import logging
from datetime import date

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

THAI_MONTHS = {
    1: 'มกราคม', 2: 'กุมภาพันธ์', 3: 'มีนาคม', 4: 'เมษายน',
    5: 'พฤษภาคม', 6: 'มิถุนายน', 7: 'กรกฎาคม', 8: 'สิงหาคม',
    9: 'กันยายน', 10: 'ตุลาคม', 11: 'พฤศจิกายน', 12: 'ธันวาคม',
}

# หัวตารางตามแบบฟอร์มกองทุน — ลำดับนี้ห้ามเปลี่ยน
COLUMNS = [
    ('คำนำหน้า', 14),
    ('ชื่อ', 18),
    ('ชื่อสกุล', 18),
    ('อายุ', 8),
    ('สัญชาติ', 10),
    ('เลขบัตรประชาชน/เลขหนังสือเดินทาง', 24),
    ('ประเภทค่าจ้าง', 14),
    ('ค่าจ้าง (บาท)', 14),
    ('วันที่เริ่มงาน', 14),
    ('วันที่สิ้นสุดงาน', 14),
    ('สาเหตุที่ออกจากงาน', 22),
]


def _thai_date(value):
    """วันที่แบบไทย d/m/พ.ศ. — ว่างถ้าไม่มีค่า"""
    if not value:
        return ''
    return '%d/%d/%d' % (value.day, value.month, value.year + 543)


class WelfareFundReport(models.Model):
    _name = 'welfare.fund.report'
    _description = 'รายงานหักเงินสงเคราะห์ลูกจ้าง'
    _order = 'year desc, month desc, company_id'

    name = fields.Char(string='ชื่อรายงาน', compute='_compute_name', store=True)
    month = fields.Integer(string='เดือน', required=True)
    year = fields.Char(string='ปี (ค.ศ.)', required=True)
    company_id = fields.Many2one(
        'res.company', string='สังกัด (สถานประกอบการ)', required=True, index=True)
    period_id = fields.Many2one('payroll.period', string='รอบทำเงินเดือน', ondelete='set null')

    submit_date = fields.Date(
        string='วันที่ดำเนินการนำส่ง',
        help='ใส่วันที่ที่นำส่งเงินจริง — เว้นว่างได้ ในไฟล์จะเว้นให้กรอกเอง')

    line_ids = fields.One2many('welfare.fund.report.line', 'report_id', string='รายชื่อพนักงาน')
    employee_count = fields.Integer(string='จำนวนพนักงาน', compute='_compute_totals', store=True)
    total_welfare = fields.Float(string='รวมเงินสงเคราะห์ที่หัก', compute='_compute_totals', store=True)
    total_wage = fields.Float(string='รวมค่าจ้าง', compute='_compute_totals', store=True)

    file_data = fields.Binary(string='ไฟล์ Excel', readonly=True, attachment=True)
    file_name = fields.Char(string='ชื่อไฟล์', readonly=True)
    generated_at = fields.Datetime(string='สร้างไฟล์ล่าสุดเมื่อ', readonly=True)
    note = fields.Text(string='หมายเหตุ')

    _sql_constraints = [
        ('month_year_company_uniq', 'unique(month, year, company_id)',
         'มีรายงานของเดือน/ปี/สังกัดนี้อยู่แล้ว'),
    ]

    # ------------------------------------------------------------------
    @api.depends('month', 'year', 'company_id')
    def _compute_name(self):
        for rec in self:
            month_name = THAI_MONTHS.get(rec.month, rec.month or '-')
            year_th = (int(rec.year) + 543) if (rec.year or '').isdigit() else (rec.year or '-')
            rec.name = 'เงินสงเคราะห์ %s %s - %s' % (
                month_name, year_th, rec.company_id.name or '-')

    @api.depends('line_ids', 'line_ids.welfare_amount', 'line_ids.wage')
    def _compute_totals(self):
        for rec in self:
            rec.employee_count = len(rec.line_ids)
            rec.total_welfare = sum(rec.line_ids.mapped('welfare_amount'))
            rec.total_wage = sum(rec.line_ids.mapped('wage'))

    # ------------------------------------------------------------------
    # ดึงข้อมูลจากสลิปของรอบนั้น
    # ------------------------------------------------------------------
    def _collect_lines(self):
        """รายชื่อ + ข้อมูลของคนที่ถูกหักเงินสงเคราะห์ในเดือน/ปี/สังกัดนี้"""
        self.ensure_one()
        payrolls = self.env['payroll.salary'].sudo().search([
            ('month', '=', self.month),
            ('year', '=', self.year),
            ('company_id', '=', self.company_id.id),
            ('expense_welfare_fund', '>', 0),
        ])

        vals = []
        for payroll in payrolls.sorted(lambda p: p.employee_code or ''):
            emp = payroll.employee_id
            foreigner = emp.nationality == 'ต่างชาติ'
            # ต่างชาติใช้เลขหนังสือเดินทาง ถ้าไม่มีค่อยตกมาใช้เลขบัตร (บางคนมีบัตรชมพู)
            id_number = (emp.passport_number or emp.id_card_number) if foreigner \
                else (emp.id_card_number or emp.passport_number)
            vals.append((0, 0, {
                'employee_id': emp.id,
                'prefix': emp.prefix_th or '',
                'firstname': emp.firstname or '',
                'lastname': emp.lastname or '',
                'age': self._employee_age(emp),
                'nationality': emp.nationality or '',
                'id_number': id_number or '',
                'wage_type': 'รายวัน' if emp.employee_type == 'รายวัน' else 'รายเดือน',
                'wage': emp.salary or 0.0,
                'start_date': emp.start_date or False,
                'end_date': emp.resign_date or False,
                'welfare_amount': payroll.expense_welfare_fund or 0.0,
                'welfare_base': payroll.welfare_fund_base or 0.0,
            }))
        return vals

    @staticmethod
    def _employee_age(employee):
        """อายุ ณ วันนี้ — คำนวณจากวันเกิดก่อน เผื่อช่องอายุยังไม่ได้อัปเดต"""
        birthdate = employee.birthdate
        if birthdate:
            today = date.today()
            return today.year - birthdate.year - (
                (today.month, today.day) < (birthdate.month, birthdate.day))
        return employee.age or 0

    def action_refresh_lines(self):
        """ดึงรายชื่อใหม่จากสลิปของรอบนั้น (ข้อมูลที่แก้เองในตารางจะถูกเขียนทับ)"""
        for rec in self:
            rec.line_ids.unlink()
            rec.line_ids = rec._collect_lines()
        return True

    # ------------------------------------------------------------------
    # ไฟล์ Excel
    # ------------------------------------------------------------------
    def action_export_excel(self):
        self.ensure_one()
        self._build_file()
        if not self.file_data:
            raise UserError('ยังไม่มีรายชื่อพนักงานในรายงานนี้')
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file_data/%s?download=true' % (
                self._name, self.id, self.file_name),
            'target': 'self',
        }

    def _build_file(self):
        """สร้างไฟล์ Excel ตามแบบฟอร์มกองทุน — ไม่มีรายชื่อก็ไม่สร้างไฟล์"""
        import xlsxwriter

        for rec in self:
            if not rec.line_ids:
                rec.write({'file_data': False, 'file_name': False})
                continue

            output = io.BytesIO()
            book = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = book.add_worksheet('เงินสงเคราะห์')

            base = {'font_name': 'TH SarabunPSK', 'font_size': 14}
            f_label = book.add_format(dict(base, bold=True))
            f_text = book.add_format(base)
            f_header = book.add_format(dict(base, bold=True, border=1, align='center',
                                            valign='vcenter', text_wrap=True, bg_color='#F2F2F2'))
            f_cell = book.add_format(dict(base, border=1))
            f_center = book.add_format(dict(base, border=1, align='center'))
            f_money = book.add_format(dict(base, border=1, num_format='#,##0.00'))

            year_th = (int(rec.year) + 543) if (rec.year or '').isdigit() else rec.year
            sheet.write(0, 0, 'ชื่อสถานประกอบการ', f_label)
            sheet.write(0, 1, rec.company_id.name or '', f_text)
            sheet.write(1, 0, 'รอบการส่งเงิน ปี พ.ศ.', f_label)
            sheet.write(1, 1, year_th, f_text)
            sheet.write(1, 2, 'เดือน', f_label)
            sheet.write(1, 3, THAI_MONTHS.get(rec.month, ''), f_text)
            sheet.write(2, 0, 'วันที่ดำเนินการนำส่ง', f_label)
            sheet.write(2, 1, _thai_date(rec.submit_date), f_text)

            for col, (title, width) in enumerate(COLUMNS):
                sheet.set_column(col, col, width)
                sheet.write(3, col, title, f_header)

            row = 4
            for line in rec.line_ids:
                sheet.write(row, 0, line.prefix or '', f_cell)
                sheet.write(row, 1, line.firstname or '', f_cell)
                sheet.write(row, 2, line.lastname or '', f_cell)
                sheet.write(row, 3, line.age or 0, f_center)
                sheet.write(row, 4, line.nationality or '', f_center)
                # เลขบัตร/พาสปอร์ตเป็นข้อความ ไม่งั้น Excel ตัดศูนย์นำหน้าทิ้ง
                sheet.write_string(row, 5, line.id_number or '', f_cell)
                sheet.write(row, 6, line.wage_type or '', f_center)
                sheet.write(row, 7, line.wage or 0.0, f_money)
                sheet.write(row, 8, _thai_date(line.start_date), f_center)
                sheet.write(row, 9, _thai_date(line.end_date), f_center)
                sheet.write(row, 10, line.resign_reason or '', f_cell)
                row += 1

            sheet.freeze_panes(4, 0)
            book.close()

            rec.write({
                'file_data': base64.b64encode(output.getvalue()),
                'file_name': 'เงินสงเคราะห์_%s_%s_%s.xlsx' % (
                    rec.company_id.name or '', THAI_MONTHS.get(rec.month, rec.month), year_th),
                'generated_at': fields.Datetime.now(),
            })
        return True

    # ------------------------------------------------------------------
    # สร้างอัตโนมัติจากรอบทำเงินเดือน
    # ------------------------------------------------------------------
    @api.model
    def generate_for_period(self, period):
        """สร้าง/อัพเดตรายงานของรอบนี้ แยกตามสังกัด แล้วออกไฟล์ให้เลย

        คืนจำนวนรายงานที่มีรายชื่อ — รอบที่ยังไม่ถึงเดือนเริ่มหักจะไม่มีใครถูกหัก
        จึงไม่มีรายงานถูกสร้าง
        """
        year = str(period.year)
        payrolls = self.env['payroll.salary'].sudo().search([
            ('month', '=', period.month),
            ('year', '=', year),
            ('expense_welfare_fund', '>', 0),
        ])
        companies = payrolls.mapped('company_id')

        made = 0
        for company in companies:
            report = self.sudo().search([
                ('month', '=', period.month),
                ('year', '=', year),
                ('company_id', '=', company.id),
            ], limit=1)
            if not report:
                report = self.sudo().create({
                    'month': period.month,
                    'year': year,
                    'company_id': company.id,
                    'period_id': period.id,
                })
            elif not report.period_id:
                report.period_id = period.id
            report.action_refresh_lines()
            report._build_file()
            made += 1

        # สังกัดที่เคยมีรายงานแต่รอบนี้ไม่มีใครถูกหักแล้ว → ล้างให้ว่าง
        stale = self.sudo().search([
            ('month', '=', period.month),
            ('year', '=', year),
            ('company_id', 'not in', companies.ids),
        ])
        for report in stale:
            report.action_refresh_lines()
            report._build_file()
        return made


class WelfareFundReportLine(models.Model):
    _name = 'welfare.fund.report.line'
    _description = 'รายชื่อในรายงานหักเงินสงเคราะห์ลูกจ้าง'
    _order = 'employee_code'

    report_id = fields.Many2one('welfare.fund.report', string='รายงาน',
                                required=True, ondelete='cascade')
    company_id = fields.Many2one(
        related='report_id.company_id', string='สังกัด', store=True, readonly=True)
    employee_id = fields.Many2one('employee.salary', string='พนักงาน', ondelete='set null')
    employee_code = fields.Char(related='employee_id.employee_code', string='รหัสพนักงาน',
                                store=True, readonly=True)

    prefix = fields.Char(string='คำนำหน้า')
    firstname = fields.Char(string='ชื่อ')
    lastname = fields.Char(string='ชื่อสกุล')
    age = fields.Integer(string='อายุ')
    nationality = fields.Char(string='สัญชาติ')
    id_number = fields.Char(string='เลขบัตรประชาชน/เลขหนังสือเดินทาง')
    wage_type = fields.Char(string='ประเภทค่าจ้าง')
    wage = fields.Float(string='ค่าจ้าง (บาท)')
    start_date = fields.Date(string='วันที่เริ่มงาน')
    end_date = fields.Date(string='วันที่สิ้นสุดงาน')
    resign_reason = fields.Char(
        string='สาเหตุที่ออกจากงาน',
        help='กรอกเองได้ — ระบบไม่ได้เก็บสาเหตุการออกจากงานไว้ในบัตรพนักงาน')

    welfare_amount = fields.Float(string='เงินสงเคราะห์ที่หัก')
    welfare_base = fields.Float(string='ฐานคำนวณ')
