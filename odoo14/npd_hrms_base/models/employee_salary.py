# -*- coding: utf-8 -*-
"""บัตรพนักงาน (employee.salary)

คงชื่อโมเดลเดิมจาก Odoo 14 ไว้ เพราะทั้งเอนจิน payroll, โมดูลลงเวลา และแอป HR
อ้างชื่อนี้อยู่ — เปลี่ยนแต่ข้างใน:

* ตัด PHP sync ออกทั้งหมด (เดิมทุก create/write/unlink ยิงไป npdhrms.com)
* branch_id → res.branch, company (Selection) → company_id (res.company)
* รหัสพนักงาน / ประกันสังคม / วันตัดรอบ อ่านจากนโยบายบริษัท
"""
import calendar
import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

BANK_SELECTION = [
    ('KBANK', 'KBANK - ธนาคารกสิกรไทย'),
    ('BBL', 'BBL - ธนาคารกรุงเทพ'),
    ('KTB', 'KTB - ธนาคารกรุงไทย'),
    ('SCB', 'SCB - ธนาคารไทยพาณิชย์'),
    ('BAY', 'BAY - ธนาคารกรุงศรีอยุธยา'),
    ('TTB', 'TTB - ธนาคารทหารไทยธนชาต'),
    ('GSB', 'GSB - ธนาคารออมสิน'),
    ('UOB', 'UOB - ธนาคารยูโอบี'),
    ('CIMBT', 'CIMB - ธนาคารซีไอเอ็มบีไทย'),
    ('KKP', 'KKP - ธนาคารเกียรตินาคินภัทร'),
    ('LHBANK', 'LHBANK - ธนาคารแลนด์ แอนด์ เฮ้าส์'),
    ('TISCO', 'TISCO - ธนาคารทิสโก้'),
    ('BAAC', 'BAAC - ธ.ก.ส.'),
    ('GHB', 'GHB - ธอส.'),
    ('ISBT', 'ISBT - ธนาคารอิสลามแห่งประเทศไทย'),
    ('PROMPTPAY', 'PromptPay - พร้อมเพย์'),
]


class EmployeeSalary(models.Model):
    _name = 'employee.salary'
    _description = 'พนักงาน'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'full_name'
    _order = 'employee_code'

    _sql_constraints = [
        ('employee_code_uniq', 'unique(employee_code)',
         'ไม่สามารถเพิ่มข้อมูลพนักงานซ้ำได้!'),
    ]

    # ------------------------------------------------------------------
    # ตัวตน / การเข้าใช้แอป
    # ------------------------------------------------------------------
    employee_code = fields.Char(
        string='รหัสพนักงาน', readonly=True, copy=False, index=True, tracking=True,
        help='สร้างอัตโนมัติตามนโยบายบริษัท (แก้ไขไม่ได้)')
    fingerprint_id = fields.Char(string='รหัสลายนิ้วมือ')
    pin = fields.Char(
        string='PIN 6 หลัก', copy=False, groups='npd_hrms_base.group_hrms_officer',
        help='ใช้ล็อกอินแอป HR — เห็นได้เฉพาะเจ้าหน้าที่บุคคลขึ้นไป')
    device_id = fields.Char(
        string='Device ID', copy=False, readonly=True,
        help='เครื่องที่ผูกไว้กับบัญชีนี้ — กดปุ่มรีเซ็ตเมื่อพนักงานเปลี่ยนเครื่อง')
    device_bound_at = fields.Datetime(string='ผูกเครื่องเมื่อ', readonly=True)
    allow_multi_login = fields.Boolean(string='อนุญาตเข้าพร้อมกัน', default=False)
    allow_offsite_time = fields.Boolean(string='อนุญาตลงเวลานอกสถานที่')
    failed_login_count = fields.Integer(
        string='ล็อกอินผิดติดกัน (ครั้ง)', default=0, readonly=True, copy=False)
    login_locked_until = fields.Datetime(
        string='ล็อกบัญชีถึง', readonly=True, copy=False)

    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True, tracking=True,
        default=lambda self: self.env.company)
    company_name = fields.Char(
        string='ชื่อบริษัท', related='company_id.name', store=True, readonly=True,
        help='ฟิลด์นี้มีไว้ให้แอปเดิมที่อ่านชื่อบริษัทเป็นข้อความใช้ต่อได้')

    # ------------------------------------------------------------------
    # ข้อมูลส่วนตัว
    # ------------------------------------------------------------------
    prefix_th = fields.Selection([
        ('นาย', 'นาย'), ('นางสาว', 'นางสาว'), ('นาง', 'นาง'),
    ], string='คำนำหน้าชื่อ')
    firstname = fields.Char(string='ชื่อ', required=True, tracking=True)
    lastname = fields.Char(string='นามสกุล', tracking=True)
    nickname = fields.Char(string='ชื่อเล่น')
    firstname_eng = fields.Char(string='ชื่อ (ENG)')
    lastname_eng = fields.Char(string='นามสกุล (ENG)')
    full_name = fields.Char(
        string='ชื่อ-นามสกุล', compute='_compute_full_name', store=True, index=True)

    nationality = fields.Selection([
        ('ไทย', 'ไทย'), ('ต่างชาติ', 'ต่างชาติ'),
    ], string='สัญชาติ', default='ไทย')
    gender = fields.Selection([('ชาย', 'ชาย'), ('หญิง', 'หญิง')], string='เพศ')
    marital_status = fields.Selection([
        ('โสด', 'โสด'), ('สมรส', 'สมรส'), ('หย่า', 'หย่า'),
    ], string='สถานะ')
    birthdate = fields.Date(string='วันเกิด')
    age = fields.Integer(string='อายุ', compute='_compute_age', store=True)
    phone_number = fields.Char(string='เบอร์โทรศัพท์')
    email = fields.Char(string='อีเมล')
    line_id = fields.Char(string='LineID ส่วนตัว')
    id_card_number = fields.Char(string='เลขประจำตัวประชาชน')
    passport_number = fields.Char(string='เลขที่หนังสือเดินทาง')
    social_security_number = fields.Char(string='เลขที่ประกันสังคม')
    address = fields.Char(string='ที่อยู่')
    personal_equipment = fields.Char(string='อุปกรณ์เบิกประจำตัว')
    employee_image = fields.Image(string='รูปภาพพนักงาน', max_width=1024, max_height=1024)

    # ------------------------------------------------------------------
    # สังกัด
    # ------------------------------------------------------------------
    branch_id = fields.Many2one(
        'res.branch', string='สาขา', index=True, tracking=True,
        domain="[('hr_use_in_hrms', '=', True)]")
    department_id = fields.Many2one('hr.department.custom', string='แผนก', tracking=True)
    position_id = fields.Many2one('hr.position.custom', string='ตำแหน่ง', tracking=True)
    employee_type = fields.Selection([
        ('ประจำ', 'ประจำ'), ('ทดลองงาน', 'ทดลองงาน'), ('รายวัน', 'รายวัน'),
    ], string='ประเภทพนักงาน', tracking=True)

    hr_employee_id = fields.Many2one(
        'hr.employee', string='พนักงาน (Odoo HR)', copy=False,
        help='ผูกกับ hr.employee เพื่อใช้ฟีเจอร์มาตรฐานของ Odoo '
             '(Attendance, Expense, Fleet) ร่วมกับข้อมูล HRMS ชุดนี้')
    user_id = fields.Many2one(
        'res.users', string='ผู้ใช้ Odoo', copy=False,
        help='เลือกผู้ใช้ในระบบแล้วชื่อ บริษัท และสาขา จะถูกดึงมาให้อัตโนมัติ '
             '— แก้ทีหลังได้ ถ้าข้อมูลฝั่ง HR ต่างจากผู้ใช้')

    # ------------------------------------------------------------------
    # ค่าจ้างและสิทธิประโยชน์
    # ------------------------------------------------------------------
    salary = fields.Float(
        string='ค่าจ้าง', tracking=True, groups='npd_hrms_base.group_hrms_payroll')
    cost_of_living = fields.Float(
        string='เงินค่าครองชีพ', groups='npd_hrms_base.group_hrms_payroll')
    position_allowance = fields.Float(
        string='เงินประจำตำแหน่ง', groups='npd_hrms_base.group_hrms_payroll')
    experience_allowance = fields.Float(
        string='เงินค่าประสบการณ์', groups='npd_hrms_base.group_hrms_payroll')
    professional_allowance = fields.Float(
        string='เงินค่าวิชาชีพ', groups='npd_hrms_base.group_hrms_payroll')
    advance_payment_type = fields.Selection([
        ('ค่าเดินทาง', 'ค่าเดินทาง'), ('ค่าเบี้ยเลี้ยง', 'ค่าเบี้ยเลี้ยง'),
    ], string='เงินเบิกล่วงหน้า')
    advance_payment_limit = fields.Float(string='วงเงินเบิกล่วงหน้า')
    auto_payroll = fields.Boolean(
        string='ทำเงินเดือน Auto', default=True,
        help='ถ้าติ๊ก ระบบจะคำนวณเงินเดือนให้อัตโนมัติ ถ้าไม่ติ๊ก ต้องทำมือ')

    # ประกันสังคม
    enable_social_security = fields.Boolean(
        string='ประกันสังคม', default=True,
        groups='npd_hrms_base.group_hrms_payroll')
    social_security_condition = fields.Selection([
        ('คิดตามฐานเงินเดือนจริงที่ได้รับ', 'คิดตามฐานเงินเดือนจริงที่ได้รับ'),
        ('คิดตามค่าคงที่', 'คิดตามค่าคงที่'),
    ], string='เงื่อนไขประกันสังคม', groups='npd_hrms_base.group_hrms_payroll')
    social_security_fixed_amount = fields.Float(
        string='ค่าคงที่ของประกันสังคม', groups='npd_hrms_base.group_hrms_payroll')
    social_security_start_date = fields.Date(
        string='เงื่อนไขที่เริ่มคำนวณประกันสังคม',
        groups='npd_hrms_base.group_hrms_payroll')

    # ภาษี
    enable_tax = fields.Boolean(
        string='ภาษี', default=True, groups='npd_hrms_base.group_hrms_payroll')
    tax_condition = fields.Selection([
        ('คิดภาษี ภงด.1 ใหม่ทุกเดือน', 'คิดภาษี ภงด.1 ใหม่ทุกเดือน'),
    ], string='เงื่อนไขภาษี', groups='npd_hrms_base.group_hrms_payroll')
    tax_exception = fields.Float(
        string='จำนวนภาษีคงที่ต่อเดือน', groups='npd_hrms_base.group_hrms_payroll')
    tax_start_date_condition = fields.Date(
        string='เงื่อนไขที่เริ่มคำนวณภาษี', groups='npd_hrms_base.group_hrms_payroll')

    # ------------------------------------------------------------------
    # การจ้างงาน
    # ------------------------------------------------------------------
    start_date = fields.Date(string='วันที่เริ่มงาน', tracking=True)
    appointment_date = fields.Date(string='วันที่บรรจุ')
    contract_end_date = fields.Date(string='วันที่สิ้นสุดสัญญาจ้าง')
    end_trial_date = fields.Date(string='วันที่สิ้นสุดทดลองงาน')
    probation_period = fields.Integer(string='ระยะเวลาทดลองงาน (วัน)')
    retirement_year = fields.Date(string='ปีที่เกษียณ')
    resign_date = fields.Date(
        string='วันที่ออกจากงาน', tracking=True,
        help='ใช้คำนวณการคืนเงินประกันการทำงาน และปิดสถานะอัตโนมัติเมื่อพ้นรอบจ่าย')
    service_duration = fields.Char(
        string='อายุงาน', compute='_compute_service_duration')

    status = fields.Selection([
        ('active', 'ใช้งาน'),
        ('inactive', 'ไม่ใช้งาน'),
    ], string='สถานะการใช้งาน', default='active', required=True, tracking=True, index=True)

    # ------------------------------------------------------------------
    # การจ่ายเงิน
    # ------------------------------------------------------------------
    payment_channel = fields.Selection([
        ('เงินสด', 'เงินสด'), ('โอนผ่านธนาคาร', 'โอนผ่านธนาคาร'),
    ], string='ช่องทางการชำระเงิน')
    transfer_type = fields.Selection([
        ('transfer', 'โอนเข้าบัญชี'),
        ('cash', 'รับเงินสด'),
    ], string='ประเภทการโอนเงิน', default='transfer')
    payment_journal_id = fields.Many2one(
        'account.journal', string='บัญชีบริษัทนำจ่าย',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help='แทนฟิลด์ payment_account_type เดิมที่เป็น Selection ค่าคงที่ '
             'ของบัญชี SCB บริษัทเดียว')
    bank_name = fields.Selection(BANK_SELECTION, string='ธนาคาร')
    bank_branch_code = fields.Char(string='รหัสสาขาธนาคาร')
    bank_account_number = fields.Char(string='เลขที่บัญชี')
    details = fields.Text(string='รายละเอียด')

    # ------------------------------------------------------------------
    # ประวัติ
    # ------------------------------------------------------------------
    behavior_ids = fields.One2many(
        'employee.work.behavior', 'employee_id', string='พฤติกรรมการทำงาน')
    work_history_image_ids = fields.One2many(
        'employee.work.history.image', 'employee_id', string='รูปภาพประวัติการทำงาน')

    # ==================================================================
    # Compute
    # ==================================================================
    @api.depends('firstname', 'lastname')
    def _compute_full_name(self):
        for rec in self:
            rec.full_name = ' '.join(
                part for part in (rec.firstname, rec.lastname) if part) or ''

    @api.depends('full_name', 'employee_code')
    def _compute_display_name(self):
        """Odoo 18 ใช้ _compute_display_name แทน name_get ของ Odoo 14"""
        for rec in self:
            if rec.employee_code and rec.full_name:
                rec.display_name = '[%s] %s' % (rec.employee_code, rec.full_name)
            else:
                rec.display_name = rec.full_name or rec.employee_code or _('พนักงานใหม่')

    @api.depends('birthdate')
    def _compute_age(self):
        """Odoo 14 ให้กรอกอายุมือแล้วไม่เคยอัปเดต — เปลี่ยนเป็นคำนวณจากวันเกิด"""
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.birthdate and rec.birthdate <= today:
                rec.age = relativedelta(today, rec.birthdate).years
            else:
                rec.age = 0

    @api.depends('start_date', 'resign_date')
    def _compute_service_duration(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.start_date:
                rec.service_duration = ''
                continue
            end = rec.resign_date or today
            if end < rec.start_date:
                rec.service_duration = ''
                continue
            delta = relativedelta(end, rec.start_date)
            rec.service_duration = '%d ปี %d เดือน %d วัน' % (
                delta.years, delta.months, delta.days)

    # ==================================================================
    # Onchange / Constraints
    # ==================================================================
    @api.onchange('salary', 'company_id')
    def _onchange_salary_set_sso(self):
        """กรอกค่าจ้าง → ตั้งเงื่อนไขและค่าคงที่ประกันสังคมให้อัตโนมัติ

        อัตราและเพดานอ่านจากนโยบายบริษัท (Odoo 14 ฝัง 5% / 1,650 / 17,500 ไว้ในโค้ด)
        """
        for rec in self:
            if not rec.salary or rec.salary <= 0:
                continue
            company = rec.company_id or self.env.company
            if not company.hrms_sso_enabled:
                continue
            if not rec.social_security_condition:
                rec.social_security_condition = 'คิดตามฐานเงินเดือนจริงที่ได้รับ'
            policy = company._hrms_policy()
            effective_wage = max(min(rec.salary, policy['sso_max']), policy['sso_min'])
            rec.social_security_fixed_amount = round(
                effective_wage * policy['sso_rate'], 2)

    @api.onchange('user_id')
    def _onchange_user_id(self):
        """เลือกผู้ใช้ในระบบ → ดึงชื่อ บริษัท สาขา และข้อมูลติดต่อมาให้

        เดิมต้องพิมพ์ชื่อเองทั้งที่ผู้ใช้ในระบบมีข้อมูลครบอยู่แล้ว ทำให้สะกดไม่ตรงกัน
        และต้องมาจับคู่ทีหลัง — ตอนนี้เลือกครั้งเดียวได้ครบ

        เขียนทับเฉพาะช่องที่ยังว่าง ยกเว้นชื่อ/บริษัท/สาขาที่ตั้งใจให้ยึดตามผู้ใช้
        เพื่อไม่ให้ค่าที่ฝ่ายบุคคลแก้ไว้เองหายไปตอนเผลอแตะฟิลด์นี้
        """
        for rec in self:
            user = rec.user_id
            if not user:
                continue

            # ถ้าติดตั้ง partner_firstname ไว้ ผู้ใช้จะมีชื่อ/นามสกุลแยกกันอยู่แล้ว
            # → อ่านตรง ๆ แม่นกว่าการเดาจากช่องว่าง (ชื่อกลาง คำนำหน้า หรือ
            #   นามสกุลที่มีช่องว่าง จะตัดผิดทันที)
            # ไม่มีโมดูลนั้นค่อย fallback ไปตัดจาก name
            first = getattr(user, 'firstname', False)
            last = getattr(user, 'lastname', False)
            if first or last:
                rec.firstname = first or False
                rec.lastname = last or False
            elif user.name:
                parts = user.name.strip().split(' ', 1)
                rec.firstname = parts[0]
                rec.lastname = parts[1] if len(parts) > 1 else False

            if user.company_id:
                rec.company_id = user.company_id
            # สาขาเริ่มต้นของผู้ใช้ (มาจากโมดูลจัดการหลายสาขา)
            user_branch = getattr(user, 'branch_id', False)
            if user_branch:
                rec.branch_id = user_branch

            if not rec.email:
                rec.email = user.email or False
            if not rec.phone_number:
                rec.phone_number = user.phone or getattr(user, 'mobile', False) or False
            if not rec.employee_image and user.image_1920:
                rec.employee_image = user.image_1920

    @api.constrains('user_id')
    def _check_user_unique(self):
        """ผู้ใช้หนึ่งคนผูกได้กับบัตรพนักงานใบเดียว

        ถ้าผูกซ้ำ ระบบจะหาไม่ถูกว่าคนที่ล็อกอินอยู่คือพนักงานคนไหน
        (มีผลกับสิทธิ์ "เห็นเฉพาะข้อมูลตัวเอง" และสายอนุมัติ)
        """
        for rec in self:
            if not rec.user_id:
                continue
            duplicate = self.with_context(active_test=False).sudo().search([
                ('user_id', '=', rec.user_id.id), ('id', '!=', rec.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    'ผู้ใช้ "%s" ถูกผูกกับพนักงาน %s (%s) อยู่แล้ว'
                    % (rec.user_id.name, duplicate.full_name or '',
                       duplicate.employee_code or ''))

    @api.constrains('pin')
    def _check_pin(self):
        """PIN ต้องเป็นตัวเลข 6 หลัก และห้ามซ้ำกันทั้งระบบ

        ความซ้ำสำคัญกว่าที่คิด: แอปล็อกอินด้วย PIN อย่างเดียว (ไม่มี username)
        ถ้า PIN ซ้ำ ระบบจะไม่มีทางรู้ว่าเป็นใคร — ของเดิมฝั่ง PHP ใช้
        ``ORDER BY id DESC LIMIT 1`` ซึ่งแปลว่าคนที่สมัครทีหลังแย่งบัญชีคนก่อนได้
        """
        for rec in self:
            if not rec.pin:
                continue
            if not rec.pin.isdigit() or len(rec.pin) != 6:
                raise ValidationError('PIN ต้องเป็นตัวเลข 6 หลักเท่านั้น')
            duplicate = self.with_context(active_test=False).sudo().search([
                ('pin', '=', rec.pin), ('id', '!=', rec.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    'PIN นี้ถูกใช้โดยพนักงาน %s แล้ว กรุณาใช้ PIN อื่น'
                    % (duplicate.employee_code or duplicate.full_name or ''))

    @api.constrains('id_card_number')
    def _check_id_card_number(self):
        for rec in self:
            if not rec.id_card_number:
                continue
            digits = rec.id_card_number.replace('-', '').replace(' ', '')
            if not digits.isdigit() or len(digits) != 13:
                raise ValidationError(
                    'เลขประจำตัวประชาชนต้องเป็นตัวเลข 13 หลัก (%s)' % rec.id_card_number)

    @api.constrains('resign_date', 'start_date')
    def _check_resign_after_start(self):
        for rec in self:
            if rec.resign_date and rec.start_date and rec.resign_date < rec.start_date:
                raise ValidationError('วันที่ออกจากงานต้องไม่ก่อนวันที่เริ่มงาน')

    # ==================================================================
    # รหัสพนักงาน
    # ==================================================================
    @api.model
    def _generate_employee_code(self, company=None):
        """หาเลขว่างตัวแรกตั้งแต่เลขเริ่มต้นของบริษัท แล้วจัดรูปแบบตามนโยบาย

        คงพฤติกรรมเดิมของ Odoo 14: เลขที่ถูกใช้ไปแล้ว (รวม record ที่ archive)
        จะถูกข้าม เพราะ SQL unique constraint ยัง enforce กับ archived อยู่
        """
        company = company or self.env.company
        policy = company._hrms_policy()
        prefix = policy['code_prefix']
        padding = policy['code_padding']

        used = set()
        rows = self.with_context(active_test=False).sudo().search_read(
            [('employee_code', '!=', False)], ['employee_code'])
        for row in rows:
            code = (row['employee_code'] or '').strip()
            if prefix and code.startswith(prefix):
                code = code[len(prefix):]
            if code.isdigit():
                used.add(int(code))

        number = policy['code_start']
        while number in used:
            number += 1
        body = str(number).zfill(padding) if padding else str(number)
        return f'{prefix}{body}'

    @api.model
    def _is_employee_code_taken(self, code):
        if not code:
            return False
        return bool(self.with_context(active_test=False).sudo().search_count(
            [('employee_code', '=', code)]))

    @api.model
    def default_get(self, fields_list):
        """โชว์รหัสตัวอย่าง (เลขถัดไป) ทันทีที่กดสร้าง

        ค่าจริงยืนยันอีกครั้งตอน create เผื่อมีคนสร้างแทรกระหว่างเปิดฟอร์มค้างไว้
        """
        res = super().default_get(fields_list)
        if 'employee_code' in fields_list and not res.get('employee_code'):
            company = self.env['res.company'].browse(
                res.get('company_id')) or self.env.company
            res['employee_code'] = self._generate_employee_code(company)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            company = self.env['res.company'].browse(
                vals.get('company_id')) or self.env.company
            code = (vals.get('employee_code') or '').strip()
            if not code or self._is_employee_code_taken(code):
                vals['employee_code'] = self._generate_employee_code(company)
        return super().create(vals_list)

    # ==================================================================
    # ปุ่มดำเนินการ
    # ==================================================================
    def action_reset_device_id(self):
        """ปลดการผูกเครื่อง — พนักงานล็อกอินจากเครื่องใหม่ได้ครั้งถัดไป

        Odoo 14 ต้องยิง PHP ไปล้างคอลัมน์ device_id ในฝั่ง MySQL ก่อน
        ตอนนี้ข้อมูลอยู่ใน Odoo แล้วจึงเขียนตรงได้
        """
        self.write({
            'device_id': False,
            'device_bound_at': False,
            'failed_login_count': 0,
            'login_locked_until': False,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'สำเร็จ',
                'message': 'รีเซ็ต Device ID สำเร็จ (%d คน)' % len(self),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_unlock_login(self):
        """ปลดล็อกบัญชีที่ถูกล็อกจากการใส่ PIN ผิดหลายครั้ง"""
        self.write({'failed_login_count': 0, 'login_locked_until': False})
        return True

    def action_generate_pin(self):
        """สุ่ม PIN 6 หลักที่ยังไม่มีใครใช้ — ใช้ตอนเปิดใช้แอปครั้งแรก"""
        import secrets
        used = {
            row['pin']
            for row in self.with_context(active_test=False).sudo().search_read(
                [('pin', '!=', False)], ['pin'])
            if row['pin']
        }
        for rec in self:
            for _attempt in range(100):
                candidate = '%06d' % secrets.randbelow(1000000)
                if candidate not in used:
                    used.add(candidate)
                    rec.pin = candidate
                    break
            else:
                raise UserError('สุ่ม PIN ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')
        return True

    def action_create_hr_employee(self):
        """สร้าง/ผูก hr.employee มาตรฐานของ Odoo ให้พนักงานคนนี้"""
        Employee = self.env['hr.employee']
        for rec in self:
            if rec.hr_employee_id:
                continue
            rec.hr_employee_id = Employee.create({
                'name': rec.full_name or rec.employee_code,
                'company_id': rec.company_id.id,
                'work_email': rec.email or False,
                'work_phone': rec.phone_number or False,
                'private_street': rec.address or False,
                'birthday': rec.birthdate or False,
            })
        return True

    def action_open_work_schedule(self):
        self.ensure_one()
        schedule = self.env['hr.work.schedule'].search(
            [('employee_id', '=', self.id)], limit=1)
        return {
            'type': 'ir.actions.act_window',
            'name': 'ตารางงาน',
            'res_model': 'hr.work.schedule',
            'view_mode': 'form',
            'res_id': schedule.id or False,
            'target': 'current',
            'context': {'default_employee_id': self.id},
        }

    # ==================================================================
    # Cron
    # ==================================================================
    @api.model
    def _cron_deactivate_resigned_employees(self):
        """ปิดสถานะพนักงานที่ลาออกและพ้นรอบจ่ายสุดท้ายไปแล้ว (รันทุกเที่ยงคืน)

        เงื่อนไข: status ยัง active + มี resign_date + resign_date < วันเริ่มรอบปัจจุบัน
        → แปลว่ารอบเงินเดือนสุดท้ายถูกตัดจ่ายไปแล้ว จึงปิดสถานะได้

        วนทีละบริษัทเพราะวันตัดรอบ (cutoff_start_day) ตั้งแยกรายบริษัทได้
        """
        today = fields.Date.context_today(self)
        total = 0
        for company in self.env['res.company'].sudo().search([]):
            cutoff_start_day = company.hrms_cutoff_start_day or 25

            # วันเริ่มรอบปัจจุบัน = วันที่ cutoff_start_day ของเดือนที่แล้ว
            if today.month == 1:
                year, month = today.year - 1, 12
            else:
                year, month = today.year, today.month - 1
            last_day_prev = calendar.monthrange(year, month)[1]
            cycle_start = date(year, month, min(cutoff_start_day, last_day_prev))

            employees = self.sudo().search([
                ('company_id', '=', company.id),
                ('status', '=', 'active'),
                ('resign_date', '!=', False),
                ('resign_date', '<', cycle_start),
            ])
            if not employees:
                continue
            employees.write({'status': 'inactive'})
            total += len(employees)
            _logger.info(
                '[CRON-DEACTIVATE] %s: ปิดสถานะพนักงานลาออก %d คน (cycle_start=%s): %s',
                company.name, len(employees), cycle_start,
                ', '.join('%s(%s)' % (e.full_name or '', e.employee_code or '')
                          for e in employees))
        if not total:
            _logger.info('[CRON-DEACTIVATE] ไม่มีพนักงานลาออกที่ต้องปิดสถานะ')
        return True

    # ==================================================================
    # Helper ที่โมดูล API / payroll เรียกใช้
    # ==================================================================
    @api.model
    def _find_by_code(self, employee_code):
        """หาพนักงานจากรหัส — จุดเดียวที่ทุกโมดูลใช้ เพื่อให้ normalize เหมือนกัน"""
        if not employee_code:
            return self.browse()
        return self.sudo().search(
            [('employee_code', '=', str(employee_code).strip())], limit=1)

    def _payroll_cycle_window(self, year, month):
        """ช่วงรอบตัดเงินเดือนของเดือนที่ระบุ → (start, end)

        รอบ = วันที่ cutoff_start_day ของเดือนก่อน ถึงวันก่อนหน้านั้นของเดือนนี้
        เช่น cutoff=25, เดือน 5/2026 → 25/04/2026 ถึง 24/05/2026
        """
        self.ensure_one()
        cutoff = (self.company_id or self.env.company).hrms_cutoff_start_day or 25
        year, month = int(year), int(month)
        last_day_curr = calendar.monthrange(year, month)[1]
        end = date(year, month, min(cutoff, last_day_curr)) - relativedelta(days=1)
        prev = date(year, month, 1) - relativedelta(months=1)
        last_day_prev = calendar.monthrange(prev.year, prev.month)[1]
        start = date(prev.year, prev.month, min(cutoff, last_day_prev))
        return start, end

    def _api_profile(self):
        """ข้อมูลพนักงานรูปแบบที่แอปใช้ — รูปแบบเดียวกับ /api/employee_info เดิม"""
        self.ensure_one()
        rec = self.sudo()
        return {
            'employee_code': rec.employee_code or '',
            'prefix_th': rec.prefix_th or '',
            'firstname': rec.firstname or '',
            'lastname': rec.lastname or '',
            'name': rec.full_name or '',
            'nickname': rec.nickname or '',
            'firstname_eng': rec.firstname_eng or '',
            'lastname_eng': rec.lastname_eng or '',
            'gender': rec.gender or '',
            'nationality': rec.nationality or '',
            'birthdate': rec.birthdate.isoformat() if rec.birthdate else '',
            'age': rec.age or 0,
            'phone_number': rec.phone_number or '',
            'email': rec.email or '',
            'marital_status': rec.marital_status or '',
            'address': rec.address or '',
            'id_card_number': rec.id_card_number or '',
            'passport_number': rec.passport_number or '',
            'social_security_number': rec.social_security_number or '',
            'company': rec.company_id.name or '',
            'company_id': rec.company_id.id,
            'branch': rec.branch_id.name or '',
            'branch_id': rec.branch_id.id or False,
            'department': rec.department_id.name or '',
            'position': rec.position_id.name or '',
            'employee_type': rec.employee_type or '',
            'salary': rec.salary or 0.0,
            'cost_of_living': rec.cost_of_living or 0.0,
            'position_allowance': rec.position_allowance or 0.0,
            'experience_allowance': rec.experience_allowance or 0.0,
            'professional_allowance': rec.professional_allowance or 0.0,
            'professional_fee': rec.professional_allowance or 0.0,
            'advance_payment_type': rec.advance_payment_type or '',
            'advance_payment_limit': rec.advance_payment_limit or 0.0,
            'start_date': rec.start_date.isoformat() if rec.start_date else '',
            'appointment_date': rec.appointment_date.isoformat() if rec.appointment_date else '',
            'contract_end_date': rec.contract_end_date.isoformat() if rec.contract_end_date else '',
            'end_trial_date': rec.end_trial_date.isoformat() if rec.end_trial_date else '',
            'probation_period': rec.probation_period or 0,
            'service_duration': rec.service_duration or '',
            'allow_offsite_time': rec.allow_offsite_time,
            'status': rec.status or '',
        }

    @api.model
    def api_get_employee_info(self, employee_code):
        """เรียกจากแอป: callKw('employee.salary', 'api_get_employee_info', [code])"""
        employee = self._find_by_code(employee_code)
        return employee._api_profile() if employee else {}


class EmployeeWorkBehavior(models.Model):
    _name = 'employee.work.behavior'
    _description = 'พฤติกรรมการทำงาน'
    _order = 'date desc, id desc'

    name = fields.Char(string='พฤติกรรมการทำงาน', required=True)
    date = fields.Date(string='วันที่บันทึก', default=fields.Date.context_today)
    kind = fields.Selection([
        ('positive', 'ชมเชย'),
        ('neutral', 'บันทึกทั่วไป'),
        ('negative', 'ต้องปรับปรุง'),
    ], string='ประเภท', default='neutral')
    note = fields.Text(string='รายละเอียด')
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', ondelete='cascade', required=True)


class EmployeeWorkHistoryImage(models.Model):
    _name = 'employee.work.history.image'
    _description = 'รูปภาพประวัติการทำงาน'

    name = fields.Char(string='ชื่อไฟล์')
    image = fields.Image(string='รูปภาพ', required=True, max_width=1920, max_height=1920)
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', ondelete='cascade', required=True)
