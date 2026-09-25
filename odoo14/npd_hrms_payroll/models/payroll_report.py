# -*- coding: utf-8 -*-
"""รายงานเงินเดือนรวมทุกช่อง — เทียบเท่ารายงานฝั่งเว็บเดิม

ฝั่งระบบเดิมมีหน้ารายงานที่กางรายได้และรายการหักออกทุกช่อง จัดกลุ่มเป็น
บริษัท > สาขา > แผนก แล้วสรุปยอดท้ายแต่ละแผนกและท้ายรายงาน ฝั่งนี้ยังไม่มี
คนทำเงินเดือนจึงต้องกลับไปเปิดระบบเดิมทุกเดือนเพื่อดูภาพรวม

ที่นี่ทำให้ครบแบบเดียวกัน แต่ใช้วิธีของ Odoo คือเก็บเป็นระเบียนจริง แล้วให้
หน้าจอรายการจัดกลุ่มและรวมยอดให้เอง ข้อดีคือกรอง จัดกลุ่มใหม่ หรือส่งออก
ได้ตามต้องการโดยไม่ต้องแก้โปรแกรม และยอดรวมของทุกช่องจะตรงกันเสมอเพราะ
มาจากตัวเลขชุดเดียวกัน

ยอดทุกช่องคัดลอกมาจากสลิปที่คำนวณแล้ว ไม่คำนวณซ้ำ รายงานจึงตรงกับสลิปเสมอ
"""
import base64
import io
import logging
from collections import OrderedDict

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

THAI_MONTHS = {
    1: 'มกราคม', 2: 'กุมภาพันธ์', 3: 'มีนาคม', 4: 'เมษายน',
    5: 'พฤษภาคม', 6: 'มิถุนายน', 7: 'กรกฎาคม', 8: 'สิงหาคม',
    9: 'กันยายน', 10: 'ตุลาคม', 11: 'พฤศจิกายน', 12: 'ธันวาคม',
}

# ลำดับคอลัมน์ของรายงาน — (ชื่อฟิลด์บนบรรทัดรายงาน, หัวคอลัมน์)
# ใช้ชุดเดียวกันทั้งหน้าจอและไฟล์ Excel เพื่อไม่ให้สองที่หลุดจากกัน
# เรียงตามรายงานฝั่งเดิมทุกช่อง เพื่อให้คนที่ใช้อยู่เดิมอ่านได้ทันที
REPORT_COLUMNS = [
    ('base_salary', 'เงินเดือน'),
    ('income_position_allowance', 'เงินประจำตำแหน่ง'),
    ('income_experience_allowance', 'ค่าประสบการณ์'),
    ('income_professional_allowance', 'ค่าวิชาชีพ'),
    ('income_cost_of_living', 'ค่าครองชีพ'),
    ('ot_total_weekday', 'ค่าล่วงเวลา/โอที'),
    ('ot_total_holiday', 'ค่าล่วงเวลา/วันหยุดนักขัตฤกษ์'),
    ('ot_total_sunday', 'ค่าล่วงเวลา/วันอาทิตย์'),
    ('income_allowance', 'เบี้ยเลี้ยง'),
    ('income_food', 'ค่าอาหาร'),
    ('income_transport', 'ค่าเดินทาง/ค่าเที่ยว'),
    ('income_fuel', 'อินเซนทีฟ'),
    ('income_commission_total', 'คอมมิชชั่น'),
    ('income_other', 'รายได้อื่นๆ'),
    ('total_gross', 'รวมรายรับ'),
    ('deduction_late', 'สาย'),
    ('deduction_leave', 'ลากิจ'),
    ('missed_days_deduction', 'ขาดงาน'),
    ('tax_monthly', 'ภาษีหัก ณ ที่จ่าย'),
    ('sso_total', 'ประกันสังคม'),
    ('expense_provident', 'กองทุนสำรองเลี้ยงชีพ'),
    ('expense_advance', 'เบิกเงินล่วงหน้า'),
    ('expense_loan', 'เงินกู้'),
    ('expense_welfare_fund', 'หักเงินสงเคราะห์ลูกจ้าง'),
    ('expense_ksl', 'กยศ.'),
    ('expense_other', 'หักอื่นๆ'),
    ('total_deduction', 'รวมรายหัก'),
    ('net_salary', 'เงินได้สุทธิ'),
]


class PayrollReport(models.Model):
    _name = 'payroll.report'
    _description = 'รายงานเงินเดือน'
    _order = 'year desc, month desc, id desc'
    _rec_name = 'display_name'

    month = fields.Integer(string='เดือน', required=True,
                           default=lambda self: fields.Date.context_today(self).month)
    year = fields.Char(string='ปี (ค.ศ.)', required=True,
                       default=lambda self: str(fields.Date.context_today(self).year))
    company_id = fields.Many2one(
        'res.company', string='บริษัท',
        help='เว้นว่าง = ออกรายงานรวมทุกบริษัทที่มีสิทธิ์เห็น')

    line_ids = fields.One2many('payroll.report.line', 'report_id',
                               string='รายชื่อพนักงาน')
    employee_count = fields.Integer(string='จำนวนพนักงาน',
                                    compute='_compute_totals', store=True)
    total_gross = fields.Float(string='รวมรายรับทั้งหมด',
                               compute='_compute_totals', store=True, digits=(16, 2))
    total_deduction = fields.Float(string='รวมรายหักทั้งหมด',
                                   compute='_compute_totals', store=True, digits=(16, 2))
    total_net = fields.Float(string='รวมเงินได้สุทธิ',
                             compute='_compute_totals', store=True, digits=(16, 2))

    generated_at = fields.Datetime(string='ดึงข้อมูลล่าสุดเมื่อ', readonly=True)
    file_data = fields.Binary(string='ไฟล์ Excel', readonly=True, attachment=True)
    file_name = fields.Char(string='ชื่อไฟล์', readonly=True)

    display_name = fields.Char(compute='_compute_display_name', store=False)
    month_name = fields.Char(string='ชื่อเดือน', compute='_compute_labels')
    year_th = fields.Char(string='ปี พ.ศ.', compute='_compute_labels')

    @api.depends('month', 'year')
    def _compute_labels(self):
        """ชื่อเดือนไทยกับปี พ.ศ. — ใช้แสดงบนหัวรายงาน"""
        for rec in self:
            rec.month_name = THAI_MONTHS.get(rec.month, str(rec.month or '-'))
            rec.year_th = rec._year_th()

    @api.depends('month', 'year', 'company_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = 'รายงานเงินเดือน %s %s — %s' % (
                THAI_MONTHS.get(rec.month, rec.month or '-'),
                rec._year_th(), rec.company_id.name or 'ทุกบริษัท')

    def _year_th(self):
        try:
            return str(int(self.year) + 543)
        except (TypeError, ValueError):
            return self.year or '-'

    @api.depends('line_ids', 'line_ids.total_gross', 'line_ids.total_deduction',
                 'line_ids.net_salary')
    def _compute_totals(self):
        for rec in self:
            rec.employee_count = len(rec.line_ids)
            rec.total_gross = sum(rec.line_ids.mapped('total_gross'))
            rec.total_deduction = sum(rec.line_ids.mapped('total_deduction'))
            rec.total_net = sum(rec.line_ids.mapped('net_salary'))

    # ------------------------------------------------------------------
    def _slip_domain(self):
        self.ensure_one()
        domain = [('month', '=', self.month), ('year', '=', self.year)]
        if self.company_id:
            domain.append(('company_id', '=', self.company_id.id))
        return domain

    def action_refresh_lines(self):
        """ดึงสลิปของงวดนี้มาสร้างบรรทัดรายงานใหม่ทั้งหมด

        ลบของเดิมทิ้งก่อนเสมอ เพราะถ้ามีการแก้สลิปหรือลบพนักงานออกจากงวด
        การไล่อัปเดตทีละแถวจะเหลือขยะค้างไว้โดยไม่มีใครรู้
        """
        for rec in self:
            rec.line_ids.unlink()
            slips = self.env['payroll.salary'].search(
                rec._slip_domain(),
                order='company_id, branch_id, department_id, employee_code')
            if not slips:
                raise UserError(_(
                    'ไม่พบสลิปเงินเดือนของเดือน %s ปี %s%s\n'
                    'กรุณาตรวจว่าทำเงินเดือนงวดนี้แล้วหรือยัง'
                ) % (THAI_MONTHS.get(rec.month, rec.month), rec._year_th(),
                     ' บริษัท %s' % rec.company_id.name if rec.company_id else ''))

            self.env['payroll.report.line'].create([
                rec._line_values(slip) for slip in slips])
            rec.generated_at = fields.Datetime.now()
        return True

    def _line_values(self, slip):
        """คัดลอกยอดจากสลิปมาเป็นบรรทัดรายงาน"""
        self.ensure_one()
        values = {
            'report_id': self.id,
            'slip_id': slip.id,
            'employee_id': slip.employee_id.id,
            'employee_code': slip.employee_code,
            'employee_name': slip.employee_id.display_name,
            'company_id': slip.company_id.id,
            'branch_id': slip.branch_id.id,
            'department_id': slip.department_id.id,
            # ฝั่งเดิมรวมค่าคอมสาขากับค่าคอมการขายไว้ช่องเดียว จึงรวมให้เหมือนกัน
            'income_commission_total': (slip.income_commission or 0.0)
                                       + (slip.income_commission_sale or 0.0),
        }
        for field_name, _label in REPORT_COLUMNS:
            if field_name == 'income_commission_total':
                continue
            values[field_name] = slip[field_name] or 0.0
        return values

    # ------------------------------------------------------------------
    def action_open_lines(self):
        """เปิดรายการแบบจัดกลุ่ม บริษัท > สาขา > แผนก พร้อมยอดรวมทุกช่อง"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.display_name,
            'res_model': 'payroll.report.line',
            'view_mode': 'list,pivot',
            'domain': [('report_id', '=', self.id)],
            'context': {
                'search_default_group_company': 1,
                'search_default_group_branch': 1,
                'search_default_group_department': 1,
            },
        }

    def get_report_html(self):
        """คืน HTML ของตารางรายงาน ให้หน้าจอฝั่งเบราว์เซอร์เอาไปแสดง

        ใช้เทมเพลตตัวเดียวกับที่ใช้ตอนพิมพ์ จึงไม่มีทางที่หน้าจอกับกระดาษ
        จะแสดงตัวเลขต่างกัน
        """
        self.ensure_one()
        html, _dummy = self.env['ir.actions.report'].sudo()._render_qweb_html(
            'npd_hrms_payroll.report_payroll_html_document', self.ids)
        return html.decode() if isinstance(html, bytes) else html

    def action_export_excel(self):
        """สร้างไฟล์ Excel หน้าตาเดียวกับรายงานฝั่งเดิม แล้วให้ดาวน์โหลด"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('ยังไม่มีข้อมูลในรายงาน กรุณากด "ดึงข้อมูล" ก่อน'))
        self._build_excel()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file_data/%s?download=true' % (
                self._name, self.id, self.file_name),
            'target': 'self',
        }

    def _grouped_lines(self):
        """จัดกลุ่มบรรทัดเป็น บริษัท > สาขา > แผนก โดยคงลำดับที่เรียงมาแล้ว"""
        self.ensure_one()
        grouped = OrderedDict()
        for line in self.line_ids.sorted(
                key=lambda l: (l.company_id.name or '', l.branch_id.name or '',
                               l.department_id.name or '', l.employee_code or '')):
            company = line.company_id.name or 'ไม่ระบุบริษัท'
            branch = line.branch_id.name or 'ไม่ระบุสาขา'
            department = line.department_id.name or 'ไม่ระบุแผนก'
            grouped.setdefault(company, OrderedDict()) \
                   .setdefault(branch, OrderedDict()) \
                   .setdefault(department, []).append(line)
        return grouped

    def _build_excel(self):
        self.ensure_one()
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_('เซิร์ฟเวอร์ยังไม่ได้ติดตั้งไลบรารี xlsxwriter'))

        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        sheet = book.add_worksheet('เงินเดือน %s %s' % (
            THAI_MONTHS.get(self.month, self.month), self._year_th()))

        base = {'font_name': 'Tahoma', 'font_size': 10, 'border': 1}
        f_title = book.add_format(dict(base, bold=True, font_size=12, align='center',
                                       valign='vcenter', bg_color='#1E3C72',
                                       font_color='white'))
        f_header = book.add_format(dict(base, bold=True, align='center',
                                        valign='vcenter', text_wrap=True,
                                        bg_color='#4472C4', font_color='white'))
        f_company = book.add_format(dict(base, bold=True, bg_color='#D9E2F3'))
        f_branch = book.add_format(dict(base, bg_color='#E2EFDA'))
        f_dept = book.add_format(dict(base, bg_color='#FFF2CC'))
        f_text = book.add_format(base)
        f_num = book.add_format(dict(base, num_format='#,##0.00'))
        f_sum_text = book.add_format(dict(base, bold=True, bg_color='#FCE4D6'))
        f_sum_num = book.add_format(dict(base, bold=True, bg_color='#FCE4D6',
                                         num_format='#,##0.00'))
        f_grand_text = book.add_format(dict(base, bold=True, bg_color='#4472C4',
                                            font_color='white'))
        f_grand_num = book.add_format(dict(base, bold=True, bg_color='#4472C4',
                                           font_color='white',
                                           num_format='#,##0.00'))

        headers = ['รหัสพนักงาน', 'ชื่อ-นามสกุล'] + [label for _f, label in REPORT_COLUMNS]
        last_col = len(headers) - 1

        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 1, 28)
        sheet.set_column(2, last_col, 14)
        sheet.freeze_panes(2, 2)

        row = 0
        sheet.merge_range(row, 0, row, last_col,
                          'รายงานผลการคำนวณเงินเดือนสุทธิประจำเดือน %s %s' % (
                              THAI_MONTHS.get(self.month, self.month), self._year_th()),
                          f_title)
        sheet.set_row(row, 24)

        row += 1
        for col, label in enumerate(headers):
            sheet.write(row, col, label, f_header)
        sheet.set_row(row, 54)

        grand = [0.0] * len(REPORT_COLUMNS)
        grand_count = 0

        for company, branches in self._grouped_lines().items():
            row += 1
            sheet.merge_range(row, 0, row, last_col, 'บริษัท : %s' % company, f_company)

            for branch, departments in branches.items():
                row += 1
                sheet.merge_range(row, 0, row, last_col,
                                  'สำนักงานสาขา : %s' % branch, f_branch)

                for department, lines in departments.items():
                    row += 1
                    sheet.merge_range(row, 0, row, last_col,
                                      'แผนก : %s' % department, f_dept)

                    dept = [0.0] * len(REPORT_COLUMNS)
                    for line in lines:
                        row += 1
                        sheet.write_string(row, 0, line.employee_code or '', f_text)
                        sheet.write_string(row, 1, line.employee_name or '', f_text)
                        for index, (field_name, _label) in enumerate(REPORT_COLUMNS):
                            value = line[field_name] or 0.0
                            sheet.write_number(row, index + 2, value, f_num)
                            dept[index] += value

                    row += 1
                    sheet.merge_range(row, 0, row, 1,
                                      'รวมเป็นจำนวนแผนก %s คน' % len(lines), f_sum_text)
                    for index, value in enumerate(dept):
                        sheet.write_number(row, index + 2, value, f_sum_num)
                        grand[index] += value
                    grand_count += len(lines)

        row += 1
        sheet.merge_range(row, 0, row, 1, 'รวมทั้งหมด %s คน' % grand_count, f_grand_text)
        for index, value in enumerate(grand):
            sheet.write_number(row, index + 2, value, f_grand_num)

        book.close()
        self.write({
            'file_data': base64.b64encode(stream.getvalue()),
            'file_name': 'รายงานเงินเดือน_%s_%s.xlsx' % (
                THAI_MONTHS.get(self.month, self.month), self._year_th()),
        })


class ReportPayrollHtml(models.AbstractModel):
    """ตัวป้อนข้อมูลให้หน้ารายงาน

    ส่งรายการคอลัมน์กับข้อมูลที่จัดกลุ่มแล้วไปให้เทมเพลต เพราะการจัดกลุ่ม
    สามชั้นในเทมเพลตทำได้ลำบากและอ่านยาก ทำใน Python ตรงนี้ชัดกว่า
    และใช้ชุดคอลัมน์เดียวกับไฟล์ Excel จึงไม่มีทางหลุดจากกัน
    """
    _name = 'report.npd_hrms_payroll.report_payroll_html_document'
    _description = 'ข้อมูลสำหรับหน้ารายงานเงินเดือน'

    @api.model
    def _get_report_values(self, docids, data=None):
        reports = self.env['payroll.report'].sudo().browse(docids)
        grouped = {report.id: report._grouped_lines() for report in reports}
        return {
            'doc_ids': docids,
            'doc_model': 'payroll.report',
            'docs': reports,
            'columns': REPORT_COLUMNS,
            # +3 = ลำดับ รหัสพนักงาน ชื่อ-นามสกุล ที่อยู่หน้าคอลัมน์ตัวเลข
            'col_count': len(REPORT_COLUMNS) + 3,
            'grouped': grouped,
        }


class PayrollReportLine(models.Model):
    _name = 'payroll.report.line'
    _description = 'บรรทัดรายงานเงินเดือน'
    _order = 'company_id, branch_id, department_id, employee_code'

    report_id = fields.Many2one('payroll.report', string='รายงาน', required=True,
                                ondelete='cascade', index=True)
    slip_id = fields.Many2one('payroll.salary', string='สลิปต้นทาง',
                              ondelete='set null')
    employee_id = fields.Many2one('employee.salary', string='พนักงาน',
                                  ondelete='set null')
    employee_code = fields.Char(string='รหัสพนักงาน', index=True)
    employee_name = fields.Char(string='ชื่อ-นามสกุล')
    company_id = fields.Many2one('res.company', string='บริษัท')
    branch_id = fields.Many2one('res.branch', string='สาขา')
    department_id = fields.Many2one('hr.department.custom', string='แผนก')

    # ช่องตัวเลขทุกช่อง เรียงตรงกับ REPORT_COLUMNS ข้างบน
    # ทุกช่องตั้ง aggregator='sum' ไว้ หน้าจอรายการจึงรวมยอดให้เองทุกคอลัมน์
    # ทั้งตอนจัดกลุ่มตามแผนกและตอนดูรวมทั้งหมดท้ายตาราง
    base_salary = fields.Float(string='เงินเดือน', digits=(16, 2), aggregator='sum')
    income_position_allowance = fields.Float(string='เงินประจำตำแหน่ง', digits=(16, 2), aggregator='sum')
    income_experience_allowance = fields.Float(string='ค่าประสบการณ์', digits=(16, 2), aggregator='sum')
    income_professional_allowance = fields.Float(string='ค่าวิชาชีพ', digits=(16, 2), aggregator='sum')
    income_cost_of_living = fields.Float(string='ค่าครองชีพ', digits=(16, 2), aggregator='sum')
    ot_total_weekday = fields.Float(string='ค่าล่วงเวลา/โอที', digits=(16, 2), aggregator='sum')
    ot_total_holiday = fields.Float(string='ค่าล่วงเวลา/วันหยุดนักขัตฤกษ์', digits=(16, 2), aggregator='sum')
    ot_total_sunday = fields.Float(string='ค่าล่วงเวลา/วันอาทิตย์', digits=(16, 2), aggregator='sum')
    income_allowance = fields.Float(string='เบี้ยเลี้ยง', digits=(16, 2), aggregator='sum')
    income_food = fields.Float(string='ค่าอาหาร', digits=(16, 2), aggregator='sum')
    income_transport = fields.Float(string='ค่าเดินทาง/ค่าเที่ยว', digits=(16, 2), aggregator='sum')
    income_fuel = fields.Float(string='อินเซนทีฟ', digits=(16, 2), aggregator='sum')
    income_commission_total = fields.Float(string='คอมมิชชั่น', digits=(16, 2), aggregator='sum')
    income_other = fields.Float(string='รายได้อื่นๆ', digits=(16, 2), aggregator='sum')
    total_gross = fields.Float(string='รวมรายรับ', digits=(16, 2), aggregator='sum')
    deduction_late = fields.Float(string='สาย', digits=(16, 2), aggregator='sum')
    deduction_leave = fields.Float(string='ลากิจ', digits=(16, 2), aggregator='sum')
    missed_days_deduction = fields.Float(string='ขาดงาน', digits=(16, 2), aggregator='sum')
    tax_monthly = fields.Float(string='ภาษีหัก ณ ที่จ่าย', digits=(16, 2), aggregator='sum')
    sso_total = fields.Float(string='ประกันสังคม', digits=(16, 2), aggregator='sum')
    expense_provident = fields.Float(string='กองทุนสำรองเลี้ยงชีพ', digits=(16, 2), aggregator='sum')
    expense_advance = fields.Float(string='เบิกเงินล่วงหน้า', digits=(16, 2), aggregator='sum')
    expense_loan = fields.Float(string='เงินกู้', digits=(16, 2), aggregator='sum')
    expense_welfare_fund = fields.Float(string='หักเงินสงเคราะห์ลูกจ้าง', digits=(16, 2), aggregator='sum')
    expense_ksl = fields.Float(string='กยศ.', digits=(16, 2), aggregator='sum')
    expense_other = fields.Float(string='หักอื่นๆ', digits=(16, 2), aggregator='sum')
    total_deduction = fields.Float(string='รวมรายหัก', digits=(16, 2), aggregator='sum')
    net_salary = fields.Float(string='เงินได้สุทธิ', digits=(16, 2), aggregator='sum')
