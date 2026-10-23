# -*- coding: utf-8 -*-
"""หนังสือรับรองเงินเดือน (Jasper) — คู่กับ o14 npd_salary_certificate (ผู้ใช้สั่ง 23 ต.ค. 2569)

ข้อมูลในหนังสือดึงจาก employee.salary แก้ได้ก่อนพิมพ์ · หัวกระดาษ/โลโก้จาก res.company ของพนักงาน
Jasper อ่านค่าจากฟิลด์ตรง ๆ ข้อความที่ต้องจัดรูป (พ.ศ. ตัวอักษร ย่อหน้า) จึงเตรียมเป็น jasper_* ไว้ที่นี่
"""
import re

from odoo import api, fields, models

from .thai_text import baht_text, duration_text, thai_date


class ResCompany(models.Model):
    _inherit = 'res.company'

    # หัว/ท้ายกระดาษหนังสือรับรองเงินเดือน (ตามแบบที่ฝ่ายบุคคลใช้ แก้ได้ที่บริษัท)
    hrms_cert_phone = fields.Char('โทรศัพท์ (หนังสือรับรอง)', default='02-433-5556 (สำนักงานใหญ่)')
    hrms_cert_email = fields.Char('อีเมล (หนังสือรับรอง)', default='npd9.acc@gmail.com')
    hrms_cert_website = fields.Char('เว็บไซต์ (หนังสือรับรอง)', default='www.npd9.com')
    hrms_cert_footer = fields.Char('ท้ายกระดาษ (หนังสือรับรอง)', default='ฝ่ายบุคคล สำนักงานส่วนกลาง')
    hrms_cert_footer_phone = fields.Char('โทรท้ายกระดาษ (หนังสือรับรอง)', default='02-433-5556')


class NpdSalaryCertSigner(models.Model):
    _name = 'npd.salary.cert.signer'
    _description = 'ผู้ลงนามหนังสือรับรองเงินเดือน'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    name = fields.Char('ชื่อผู้ลงนาม', required=True)
    title = fields.Char('ตำแหน่ง/ฝ่าย', default='ฝ่ายบุคคล')
    active = fields.Boolean(default=True)


class NpdSalaryCertificate(models.Model):
    _name = 'npd.salary.certificate'
    _description = 'หนังสือรับรองเงินเดือน'
    _inherit = ['mail.thread']
    _order = 'issue_date desc, id desc'

    name = fields.Char('ชื่อ', compute='_compute_name', store=True)
    employee_id = fields.Many2one('employee.salary', string='พนักงาน', required=True, tracking=True)
    issue_date = fields.Date('ออกให้ ณ วันที่', required=True, default=fields.Date.context_today, tracking=True)
    signer_id = fields.Many2one(
        'npd.salary.cert.signer', string='ผู้ลงนาม', required=True,
        default=lambda self: self.env['npd.salary.cert.signer'].search([], limit=1), tracking=True)
    purpose = fields.Char('วัตถุประสงค์ (ไม่พิมพ์)', help='บันทึกไว้ดูภายหลัง เช่น ยื่นกู้ธนาคาร')

    company_id = fields.Many2one('res.company', string='บริษัท', compute='_compute_from_employee',
                                 store=True, readonly=False)
    employee_name = fields.Char('ชื่อ-นามสกุล', compute='_compute_from_employee', store=True, readonly=False)
    position_name = fields.Char('ตำแหน่ง', compute='_compute_from_employee', store=True, readonly=False)
    salary = fields.Float('อัตราเงินเดือนล่าสุด', compute='_compute_from_employee', store=True, readonly=False,
                          digits=(16, 2))
    start_date = fields.Date('เริ่มทำงานตั้งแต่วันที่', compute='_compute_from_employee', store=True,
                             readonly=False)

    salary_text = fields.Char('จำนวนเงิน (ตัวอักษร)', compute='_compute_texts')
    start_date_text = fields.Char('วันเริ่มงาน (พ.ศ.)', compute='_compute_texts')
    issue_date_text = fields.Char('วันที่ออก (พ.ศ.)', compute='_compute_texts')
    duration = fields.Char('รวมระยะเวลา', compute='_compute_texts')

    # ส่งให้ Jasper
    company_logo = fields.Binary(related='company_id.logo', string='Logo')
    jasper_company_name = fields.Char(compute='_compute_jasper')
    jasper_company_address = fields.Char(compute='_compute_jasper')
    jasper_company_phone = fields.Char(compute='_compute_jasper')
    jasper_company_contact = fields.Char(compute='_compute_jasper')
    jasper_body = fields.Char(compute='_compute_jasper')
    jasper_issue = fields.Char(compute='_compute_jasper')
    jasper_signer_name = fields.Char(compute='_compute_jasper')
    jasper_signer_title = fields.Char(compute='_compute_jasper')
    jasper_footer = fields.Char(compute='_compute_jasper')
    jasper_footer_phone = fields.Char(compute='_compute_jasper')

    @api.depends('employee_name', 'issue_date')
    def _compute_name(self):
        for rec in self:
            rec.name = 'หนังสือรับรองเงินเดือน %s %s' % (rec.employee_name or '', thai_date(rec.issue_date))

    @staticmethod
    def _clean_position(name):
        # ตำแหน่งในระบบมีภาษาอังกฤษในวงเล็บต่อท้าย เช่น "ผู้จัดการสาขา (Branch Manager)" — หนังสือใช้ภาษาไทย
        return re.sub(r'\s*\([A-Za-z0-9 &/.,\-]+\)\s*$', '', name or '').strip()

    @api.depends('employee_id')
    def _compute_from_employee(self):
        for rec in self:
            emp = rec.employee_id
            if not emp:
                continue
            rec.employee_name = '%s%s %s' % (emp.prefix_th or '', emp.firstname or '', emp.lastname or '')
            rec.position_name = self._clean_position(emp.position_id.name)
            rec.salary = emp.salary
            rec.start_date = emp.start_date
            rec.company_id = emp.company_id

    @api.depends('salary', 'start_date', 'issue_date')
    def _compute_texts(self):
        for rec in self:
            rec.salary_text = baht_text(rec.salary)
            rec.start_date_text = thai_date(rec.start_date)
            rec.issue_date_text = thai_date(rec.issue_date)
            rec.duration = duration_text(rec.start_date, rec.issue_date)

    @staticmethod
    def _company_address(company):
        parts = [company.street, company.street2, company.city,
                 (company.state_id.name or '').replace('จ.กรุงเทพมหานคร', 'กรุงเทพมหานคร'), company.zip]
        return ' '.join(p.strip() for p in parts if p and p.strip())

    @api.depends('company_id', 'employee_name', 'position_name', 'salary', 'start_date', 'issue_date',
                 'signer_id', 'signer_id.name', 'signer_id.title')
    def _compute_jasper(self):
        for rec in self:
            c = rec.company_id
            salary = '{:,.0f}'.format(rec.salary) if rec.salary == int(rec.salary) else '{:,.2f}'.format(rec.salary)
            contact = []
            if c.hrms_cert_email:
                contact.append('E-mail : %s' % c.hrms_cert_email)
            if c.hrms_cert_website:
                contact.append('Web Site : %s' % c.hrms_cert_website)
            rec.jasper_company_name = c.name or ''
            rec.jasper_company_address = self._company_address(c)
            rec.jasper_company_phone = 'โทรศัพท์ %s' % c.hrms_cert_phone if c.hrms_cert_phone else ''
            rec.jasper_company_contact = ' , '.join(contact)
            rec.jasper_body = (
                'หนังสือฉบับนี้ให้ไว้เพื่อรับรองว่า %(name)s ปฏิบัติงานเป็นพนักงาน ในตำแหน่ง %(pos)s %(co)s '
                'มีอัตราเงินเดือนล่าสุด %(sal)s บาท (%(sal_text)s) เริ่มทำงานตั้งแต่วันที่ %(start)s '
                'จนถึงปัจจุบัน (รวมระยะเวลา %(dur)s) ซึ่งอัตรานี้ไม่รวมค่าตอบแทน และเงินพิเศษอื่นๆ'
            ) % {'name': rec.employee_name or '', 'pos': rec.position_name or '', 'co': c.name or '',
                 'sal': salary, 'sal_text': rec.salary_text, 'start': rec.start_date_text, 'dur': rec.duration}
            rec.jasper_issue = 'ออกให้ ณ วันที่ %s' % rec.issue_date_text
            rec.jasper_signer_name = '(%s)' % rec.signer_id.name if rec.signer_id else ''
            rec.jasper_signer_title = rec.signer_id.title or ''
            rec.jasper_footer = c.hrms_cert_footer or ''
            rec.jasper_footer_phone = 'โทร. %s' % c.hrms_cert_footer_phone if c.hrms_cert_footer_phone else ''

    def action_print(self):
        return self.env.ref('npd_hrms_salary_cert_jasper.jasper_salary_certificate_report').report_action(self)
