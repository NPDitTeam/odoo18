# -*- coding: utf-8 -*-
"""หนังสือรับรองการหักภาษี ณ ที่จ่าย (50 ทวิ) ของพนักงาน

ยอดเงินได้และภาษีทั้งปีดึงจากรายงาน ภ.ง.ด.1 (``pnd1.line``) โดยจับคู่จาก
เลขบัตรประชาชน ถ้าปีนั้นยังไม่มีข้อมูลใน ภ.ง.ด.1 จะถอยไปใช้ยอดจากสลิปเงินเดือน
แล้วประมาณภาษีที่ 3% เพื่อให้ออกเอกสารต่อได้ ไม่ใช่ค้างเป็นศูนย์

ต่างจากฝั่ง Odoo 14 สามอย่าง
----------------------------
* **ชื่อ/ที่อยู่/เลขผู้เสียภาษีของบริษัท ดึงจากบริษัทของพนักงาน** ไม่ใช่ค่าคงที่
  ในโค้ด ของเดิมฝังที่อยู่สำนักงานใหญ่กับเลขผู้เสียภาษีไว้ตรง ๆ ทำให้พนักงาน
  ทุกบริษัทในกลุ่มได้เอกสารที่ขึ้นบริษัทเดียวกันหมด และถ้าปล่อยเช่าให้ลูกค้า
  เอกสารของเขาจะขึ้นเป็นบริษัทเรา
* **สาขายึดตามสาขาของพนักงาน** ของเดิมบังคับเป็น "สำนักงานใหญ่" ทุกใบ
* ``states={...}`` ที่ Odoo 17 เอาออกแล้ว ย้ายไปคุมด้วย ``readonly`` ในวิวแทน
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

INCOME_TAX_FORM = [
    ('pnd1', 'ภ.ง.ด.1'),
    ('pnd1a', 'ภ.ง.ด.1ก'),
    ('pnd3', 'ภ.ง.ด.3'),
    ('pnd3a', 'ภ.ง.ด.3ก'),
    ('pnd53', 'ภ.ง.ด.53'),
]

WHT_CERT_INCOME_TYPE = [
    ('1', '1. เงินเดือน ค่าจ้าง เบี้ยเลี้ยง โบนัส ฯลฯ 40(1)'),
    ('2', '2. ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)'),
    ('3', '3. ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3)'),
    ('5', '5. ค่าจ้างทำของ ค่าบริการ ค่าเช่า ค่าขนส่ง ฯลฯ 40(7)(8)'),
    ('6', '6. อื่นๆ (ระบุ)'),
]

TAX_PAYER = [
    ('withholding', 'หักภาษี ณ ที่จ่าย'),
    ('paid_one_time', 'ออกภาษีให้ครั้งเดียว'),
]

PROVIDENT_LINE_NAME = 'กองทุนสำรองเลี้ยงชีพ'


class HRWithholdingTaxCert(models.Model):
    _name = 'hr.withholding.tax.cert'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'หนังสือรับรองการหักภาษี ณ ที่จ่าย (50 ทวิ)'
    _order = 'date desc, id desc'
    _sql_constraints = [
        ('employee_year_unique', 'UNIQUE(employee_id, report_year)',
         'มีหนังสือรับรองของพนักงานคนนี้ในปีนี้แล้ว'),
    ]

    name = fields.Char(string='เลขที่', readonly=True, copy=False,
                       default=lambda self: _('New'))
    date = fields.Date(string='วันที่', required=True,
                       default=fields.Date.context_today, tracking=True)
    state = fields.Selection([
        ('draft', 'ร่าง'), ('done', 'ยืนยันแล้ว'), ('cancel', 'ยกเลิก'),
    ], string='สถานะ', default='draft', copy=False, tracking=True)
    report_year = fields.Char(
        string='ปี (พ.ศ./ค.ศ.)', required=True, tracking=True,
        default=lambda self: str(fields.Date.context_today(self).year),
        help='ปีภาษีที่ต้องการรวมยอด เช่น 2026 หรือ 2569')

    # ------------------------------------------------------------------
    # พนักงาน
    # ------------------------------------------------------------------
    employee_id = fields.Many2one(
        'employee.salary', string='ชื่อพนักงาน', required=True,
        ondelete='restrict', tracking=True)
    employee_firstname = fields.Char(
        string='ชื่อ', related='employee_id.firstname', store=True, readonly=True)
    employee_lastname = fields.Char(
        string='นามสกุล', related='employee_id.lastname', store=True, readonly=True)
    employee_taxid = fields.Char(
        string='เลขประจำตัวผู้เสียภาษี (พนักงาน)',
        related='employee_id.id_card_number', readonly=True)
    employee_address = fields.Char(
        string='ที่อยู่ (พนักงาน)', related='employee_id.address',
        store=True, readonly=True)
    employee_resign_date = fields.Date(
        string='วันที่ออกจากงาน', related='employee_id.resign_date',
        store=True, readonly=True,
        help='ถ้าลาออกในปีภาษีนี้ ระบบจะนับยอดประกันสังคม/กองทุนสำรองเลี้ยงชีพ '
             'ถึงเดือนที่ลาออกเท่านั้น')
    pnd1_full_name = fields.Char(
        string='ชื่อ-นามสกุล (จาก ภ.ง.ด.1)', compute='_compute_pnd1_full_name',
        help='ใช้ชื่อจากรายงาน ภ.ง.ด.1 โดยจับคู่จากเลขบัตร '
             'ถ้าไม่พบใช้ชื่อจากทะเบียนพนักงานแทน')
    branch_id = fields.Many2one(
        'res.branch', string='สาขา', compute='_compute_branch',
        store=True, readonly=False,
        help='ยึดตามสาขาของพนักงาน แก้ไขเองได้')

    # ------------------------------------------------------------------
    # บริษัทผู้จ่ายเงินได้
    # ------------------------------------------------------------------
    # ทั้งสี่ช่องใช้เมธอดคำนวณเดียวกัน จึงต้องตั้ง precompute ให้ตรงกันทั้งชุด
    #   * company_id บังคับกรอก ถ้าไม่คำนวณก่อน INSERT ฐานข้อมูลปฏิเสธ not-null
    #   * ถ้าตั้ง precompute เฉพาะบางช่อง อีกสามช่องจะถูกมองว่าคำนวณแล้ว
    #     ตั้งแต่รอบ precompute แล้วไม่ถูกบันทึกลงฐานข้อมูล กลายเป็นค่าว่าง
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        compute='_compute_company', store=True, readonly=False,
        precompute=True)
    company_name = fields.Char(
        string='ชื่อบริษัท', compute='_compute_company', store=True,
        readonly=False, precompute=True)
    company_address = fields.Char(
        string='ที่อยู่บริษัท', compute='_compute_company', store=True,
        readonly=False, precompute=True)
    company_taxid = fields.Char(
        string='เลขประจำตัวผู้เสียภาษี (บริษัท)', compute='_compute_company',
        store=True, readonly=False, precompute=True)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True,
        readonly=True)

    # ------------------------------------------------------------------
    # ยอดเงิน
    # ------------------------------------------------------------------
    total_net_salary = fields.Float(
        string='เงินได้รวมทั้งปี (จาก ภ.ง.ด.1)',
        compute='_compute_total_net_salary', readonly=True)
    total_tax = fields.Float(
        string='ภาษีรวมทั้งปี (จาก ภ.ง.ด.1)',
        compute='_compute_total_net_salary', readonly=True)
    sso_amount = fields.Float(
        string='กองทุนประกันสังคม (ทั้งปี)', compute='_compute_fund_amounts',
        store=True, readonly=False,
        help='ดึงจากหน้าทำเงินเดือนให้เป็นค่าเริ่มต้น — แก้ไขเองได้')
    provident_fund_amount = fields.Float(
        string='กองทุนสำรองเลี้ยงชีพ (ทั้งปี)', compute='_compute_fund_amounts',
        store=True, readonly=False,
        help='ดึงจากหน้าทำเงินเดือนให้เป็นค่าเริ่มต้น — แก้ไขเองได้')

    income_tax_form = fields.Selection(
        INCOME_TAX_FORM, string='แบบยื่นรายการภาษี', required=True,
        default='pnd1', copy=False)
    tax_payer = fields.Selection(
        TAX_PAYER, string='ผู้จ่ายเงิน', default='withholding', required=True,
        copy=False)
    wt_line = fields.One2many(
        'hr.withholding.tax.cert.line', 'cert_id',
        string='รายการเงินได้', copy=False)

    # ==================================================================
    @api.depends('employee_id')
    def _compute_company(self):
        for rec in self:
            company = rec.employee_id.company_id or rec.company_id or self.env.company
            rec.company_id = company
            rec.company_name = company.name or ''
            rec.company_address = rec._company_address(company)
            rec.company_taxid = company.vat or ''

    @api.model
    def _company_address(self, company):
        """ที่อยู่บริษัทแบบบรรทัดเดียว รูปแบบเดียวกับหัวสลิปเงินเดือน

        คั่นด้วยเว้นวรรคไม่ใช่จุลภาค และไม่ใส่ชื่อประเทศ ให้ตรงกับ
        ธรรมเนียมการเขียนที่อยู่บนแบบฟอร์มราชการไทย
        """
        partner = company.partner_id
        state = partner.state_id.name or ''
        if state and not state.startswith(('จ.', 'กรุงเทพ')):
            state = 'จ.' + state
        parts = [partner.street, partner.street2, partner.city, state,
                 partner.zip]
        return ' '.join(p for p in parts if p)

    @api.depends('employee_id')
    def _compute_branch(self):
        for rec in self:
            rec.branch_id = rec.employee_id.branch_id

    @api.depends('employee_id', 'employee_id.id_card_number',
                 'employee_firstname', 'employee_lastname')
    def _compute_pnd1_full_name(self):
        Pnd1 = self.env['pnd1.line'].sudo()
        for rec in self:
            name = ''
            taxid = rec.employee_id.id_card_number or ''
            if taxid:
                line = Pnd1.search(
                    [('id_card_number', '=', taxid), ('full_name', '!=', False)],
                    order='pay_date desc, id desc', limit=1)
                name = (line.full_name or '').strip()
            if not name:
                name = ('%s %s' % (rec.employee_firstname or '',
                                   rec.employee_lastname or '')).strip()
            rec.pnd1_full_name = name

    # ------------------------------------------------------------------
    @api.model
    def _gregorian_year(self, report_year):
        """แปลงปีที่กรอก (ค.ศ. หรือ พ.ศ.) เป็น ค.ศ. — คืน 0 ถ้าแปลงไม่ได้"""
        try:
            y = int(report_year)
        except (TypeError, ValueError):
            return 0
        return y - 543 if y >= 2500 else y

    def _income_and_tax(self):
        """ยอดเงินได้และภาษีทั้งปีของใบนี้

        ลำดับที่ใช้: ภ.ง.ด.1 ก่อน ถ้ายังไม่มีข้อมูลค่อยถอยไปใช้สลิปเงินเดือน
        แล้วประมาณภาษี 3% — ให้ตรงกับที่ปุ่มสร้างรายการใช้ จะได้ไม่ขัดกันเอง
        """
        self.ensure_one()
        employee = self.employee_id
        if not employee or not self.report_year:
            return 0.0, 0.0
        income, tax = self.env['pnd1.line'].get_year_totals(
            employee.id_card_number, self.report_year,
            employee.company_id or self.company_id)
        if income or tax:
            return income, tax

        year = self._gregorian_year(self.report_year)
        payrolls = self.env['payroll.salary'].sudo().search([
            ('employee_id', '=', employee.id),
            ('year', 'in', [str(year), str(year + 543)]),
        ])
        income = sum(payrolls.mapped('net_salary'))
        return income, income * 3.0 / 100

    @api.depends('employee_id', 'employee_id.id_card_number', 'report_year')
    def _compute_total_net_salary(self):
        for rec in self:
            income, tax = rec._income_and_tax()
            rec.total_net_salary = income
            rec.total_tax = tax

    # ------------------------------------------------------------------
    # ประกันสังคม / กองทุนสำรองเลี้ยงชีพ
    # ------------------------------------------------------------------
    @api.model
    def _payroll_last_month(self, employee, gregorian_year):
        """เดือนสุดท้ายของปีภาษีที่นับยอดให้พนักงานคนนี้ (1-12)

        ยึดวันที่ออกจากงาน เพราะพนักงานแต่ละคนออกคนละเดือน ถ้านับ 12 เดือนหมด
        คนที่ลาออกกลางปีจะได้ยอดเกินความจริง
        """
        resign_date = employee.resign_date
        if not resign_date:
            return 12
        if resign_date.year < gregorian_year:
            return 0
        if resign_date.year == gregorian_year:
            return resign_date.month
        return 12

    def _fund_totals(self):
        self.ensure_one()
        employee = self.employee_id
        if not employee or not self.report_year:
            return 0.0, 0.0
        year = self._gregorian_year(self.report_year)
        if not year:
            return 0.0, 0.0
        last_month = self._payroll_last_month(employee, year)
        if not last_month:
            return 0.0, 0.0

        payrolls = self.env['payroll.salary'].sudo().search([
            ('employee_id', '=', employee.id),
            ('year', 'in', [str(year), str(year + 543)]),
            ('month', '<=', last_month),
        ], order='month asc')
        if not payrolls:
            return 0.0, 0.0

        # ประกันสังคม: ใช้ยอดสะสมของเดือนล่าสุด = ยอดที่หักจริงทั้งปีภาษี
        # (รวมยอดต้นรอบที่ยกมาจากระบบเก่า) ถ้าไม่มีค่อยรวมรายเดือน
        sso = payrolls[-1].accumulated_social_security or 0.0
        if not sso:
            sso = sum(payrolls.mapped('sso_total'))

        # กองทุนสำรองเลี้ยงชีพไม่มียอดสะสม — รวมรายเดือนจากบรรทัดหักในสลิป
        # ครอบคลุมทั้งแบบกรอกยอดเองและแบบคิดตามอัตรา %
        provident = 0.0
        for payroll in payrolls:
            month_pf = sum(payroll.line_ids.filtered(
                lambda l: l.type == 'deduction'
                and (l.name or '').strip() == PROVIDENT_LINE_NAME
            ).mapped('amount'))
            provident += month_pf or (payroll.expense_provident or 0.0)
        return sso, provident

    @api.depends('employee_id', 'employee_id.resign_date', 'report_year')
    def _compute_fund_amounts(self):
        for rec in self:
            sso, provident = rec._fund_totals()
            rec.sso_amount = sso
            rec.provident_fund_amount = provident

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hr.withholding.tax.cert') or _('New')
        return super().create(vals_list)

    @api.onchange('employee_id', 'report_year')
    def _onchange_employee_year(self):
        """เลือกพนักงาน/เปลี่ยนปี → สร้างรายการเงินได้ให้อัตโนมัติ"""
        if not (self.employee_id and self.report_year):
            return
        income, tax = self._income_and_tax()
        self.wt_line = [(5, 0, 0)]
        if income:
            self.wt_line = [(0, 0, {
                'wt_cert_income_type': '1',
                'wt_cert_income_desc':
                    'เงินเดือน ค่าจ้าง เบี้ยเลี้ยง โบนัส ฯลฯ 40(1)',
                'base': income,
                'wt_percent': (tax / income * 100) if income else 0.0,
                'amount': tax,
            })]

    def action_draft(self):
        return self.write({'state': 'draft'})

    def action_done(self):
        return self.write({'state': 'done'})

    def action_cancel(self):
        return self.write({'state': 'cancel'})


class HRWithholdingTaxCertLine(models.Model):
    _name = 'hr.withholding.tax.cert.line'
    _description = 'รายการเงินได้ในหนังสือรับรองหักภาษี ณ ที่จ่าย'

    cert_id = fields.Many2one(
        'hr.withholding.tax.cert', string='หนังสือรับรอง',
        index=True, ondelete='cascade')
    wt_cert_income_type = fields.Selection(
        WHT_CERT_INCOME_TYPE, string='ประเภทเงินได้', required=True)
    wt_cert_income_desc = fields.Char(string='รายละเอียดเงินได้')
    base = fields.Float(string='จำนวนเงินได้')
    wt_percent = fields.Float(string='อัตราภาษี (%)')
    amount = fields.Float(string='ภาษีที่หัก')

    @api.onchange('wt_cert_income_type')
    def _onchange_wt_cert_income_type(self):
        if self.wt_cert_income_type:
            self.wt_cert_income_desc = dict(WHT_CERT_INCOME_TYPE).get(
                self.wt_cert_income_type, '')

    @api.onchange('wt_percent', 'base')
    def _onchange_wt_percent(self):
        if self.wt_percent and self.base:
            self.amount = self.base * self.wt_percent / 100

    @api.constrains('base', 'wt_percent', 'amount')
    def _check_wt_line(self):
        for rec in self:
            if rec.wt_percent and rec.base:
                expected = rec.base * rec.wt_percent / 100
                if abs(rec.amount - expected) > 0.01:
                    raise ValidationError(_(
                        'ภาษีที่หัก (%.2f) ไม่ตรงกับ เงินได้ (%.2f) × อัตรา '
                        '(%.2f%%) = %.2f'
                    ) % (rec.amount, rec.base, rec.wt_percent, expected))
