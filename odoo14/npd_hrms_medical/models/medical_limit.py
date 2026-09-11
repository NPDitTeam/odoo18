# -*- coding: utf-8 -*-
"""วงเงินค่ารักษาพยาบาลรายบุคคล และยอดที่เบิกไปก่อนใช้ระบบ

วงเงินมี 2 ระดับ:
  1) วงเงินมาตรฐานของบริษัท — res.company.hrms_medical_annual_limit (ค่าเริ่มต้น 10,000)
  2) วงเงินเฉพาะราย ต่อปี — hrms.medical.limit (ทับวงเงินมาตรฐาน)

"รีเซตเมื่อครบปี" ไม่ได้ลบยอดเก่า — ยอดใช้ไปนับแยกตามปีของวันที่ในคำขออยู่แล้ว
(hr.manual.time.log.expense_year) ขึ้นปีใหม่จึงเริ่มนับ 0 เอง ส่วน cron ยกวงเงิน
เฉพาะรายของปีก่อนมาเป็นปีใหม่ให้ จะได้ไม่ต้องตั้งซ้ำทุกปี

ยอดยกมา (hrms.medical.opening) แยกคนละโมเดล เพราะเป็นข้อมูลเฉพาะปี ห้ามยกข้ามปี
ถ้ารวมกับวงเงินจะเผลอยกยอดเก่าไปหักซ้ำปีถัดไป
"""
import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


def _check_year_value(year):
    if not year or year < 2000 or year > 2999:
        raise ValidationError('กรุณากรอกปีเป็น ค.ศ. 4 หลัก เช่น 2026')


class HrmsMedicalLimit(models.Model):
    _name = 'hrms.medical.limit'
    _description = 'วงเงินค่ารักษาพยาบาลรายบุคคล'
    _order = 'year desc, employee_id'

    year = fields.Integer(
        string='ปี (ค.ศ.)', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True,
        ondelete='cascade', index=True)
    employee_code = fields.Char(
        related='employee_id.employee_code', string='รหัสพนักงาน', store=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', string='สาขา', store=True)
    company_id = fields.Many2one(
        related='employee_id.company_id', string='บริษัท', store=True, index=True)
    amount = fields.Float(
        string='วงเงินต่อปี (บาท)', required=True,
        default=lambda self: self.env.company.hrms_medical_annual_limit)
    standard_amount = fields.Float(
        string='วงเงินมาตรฐานของบริษัท', compute='_compute_standard_amount')
    note = fields.Char(string='หมายเหตุ')
    active = fields.Boolean(string='ใช้งาน', default=True)

    @api.depends('employee_id', 'year')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s / ปี %s' % (
                rec.employee_id.display_name or '-', rec.year or '-')

    @api.depends('employee_id')
    def _compute_standard_amount(self):
        for rec in self:
            company = rec.employee_id.company_id or self.env.company
            rec.standard_amount = company.hrms_medical_annual_limit

    @api.constrains('year')
    def _check_year(self):
        for rec in self:
            _check_year_value(rec.year)

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount < 0:
                raise ValidationError('วงเงินต่อปีต้องไม่ติดลบ')

    @api.constrains('year', 'employee_id', 'active')
    def _check_unique_per_year(self):
        """1 คน 1 ปี มีได้รายการเดียว — นับเฉพาะที่ยังใช้งาน
        (เก็บของเก่าเข้าคลังแล้วตั้งใหม่ได้)"""
        for rec in self.filtered('active'):
            if self.sudo().search_count([
                ('year', '=', rec.year),
                ('employee_id', '=', rec.employee_id.id),
                ('id', '!=', rec.id),
            ]):
                raise ValidationError(
                    'มีวงเงินของ "%s" ปี %s อยู่แล้ว — แก้ไขรายการเดิมแทนการสร้างใหม่'
                    % (rec.employee_id.display_name, rec.year))

    @api.model
    def get_limit_for(self, employee, year):
        """วงเงินที่ใช้จริงของพนักงานในปีนั้น: เฉพาะราย → มาตรฐานของบริษัท"""
        if employee:
            rec = self.sudo().search([
                ('employee_id', '=', employee.id),
                ('year', '=', year),
            ], limit=1)
            if rec:
                return rec.amount
        company = (employee and employee.company_id) or self.env.company
        return company.hrms_medical_annual_limit

    @api.model
    def _cron_rollover_annual_limit(self):
        """ยกวงเงินเฉพาะรายของปีก่อนมาเป็นปีปัจจุบัน — เฉพาะคนที่ยังไม่มีของปีนี้

        รันซ้ำกี่รอบก็ได้ผลเหมือนเดิม (ตั้งเป็นรายวันเพื่อไม่ต้องพึ่งวันที่ 1 ม.ค.)
        """
        Limit = self.sudo()
        year = fields.Date.context_today(self).year
        prev_records = Limit.search([('year', '=', year - 1)])
        if not prev_records:
            return 0
        existing = set(Limit.with_context(active_test=False).search(
            [('year', '=', year)]).mapped('employee_id').ids)
        to_create = [{
            'year': year,
            'employee_id': prev.employee_id.id,
            'amount': prev.amount,
            'note': 'ยกวงเงินมาจากปี %s อัตโนมัติ' % (year - 1),
        } for prev in prev_records if prev.employee_id.id not in existing]
        if to_create:
            Limit.create(to_create)
            _logger.info('Medical limit rollover: สร้างวงเงินปี %s ใหม่ %d รายการ',
                         year, len(to_create))
        return len(to_create)


class HrmsMedicalOpening(models.Model):
    """ยอดที่พนักงานเบิกไปแล้ว "ก่อน" เริ่มใช้ระบบนี้ (เบิกผ่านกระดาษ / Odoo 14)

    ถ้าไม่บันทึกไว้ ทุกคนจะดูเหมือนยังมีวงเงินเต็มทั้งที่เบิกไปแล้วบางส่วน
    นำเข้าจาก CSV ได้ที่ปุ่ม "นำเข้า" ของรายการ
    """
    _name = 'hrms.medical.opening'
    _description = 'ยอดค่ารักษาพยาบาลที่เบิกไปแล้วก่อนใช้ระบบ'
    _order = 'year desc, employee_id'
    _rec_name = 'employee_id'

    year = fields.Integer(
        string='ปี (ค.ศ.)', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True,
        ondelete='cascade', index=True)
    employee_code = fields.Char(
        related='employee_id.employee_code', string='รหัสพนักงาน', store=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', string='สาขา', store=True)
    company_id = fields.Many2one(
        related='employee_id.company_id', string='บริษัท', store=True, index=True)
    used_amount = fields.Float(
        string='เบิกไปแล้วก่อนใช้ระบบ (บาท)', required=True,
        help='ยอดที่เบิกไปแล้วในปีนี้ผ่านช่องทางเดิม\n'
             'ถ้ามีแต่ตัวเลข "คงเหลือ" ให้กรอก = วงเงินต่อปี − คงเหลือ')
    annual_limit = fields.Float(string='วงเงินต่อปี (บาท)', compute='_compute_preview')
    remaining_preview = fields.Float(
        string='คงเหลือหลังหัก (บาท)', compute='_compute_preview',
        help='ใช้ตรวจทานกับตัวเลขที่ HR ถืออยู่ — หักใบที่อนุมัติในระบบแล้วด้วย')
    note = fields.Char(string='หมายเหตุ')

    @api.depends('employee_id', 'year', 'used_amount')
    def _compute_preview(self):
        Log = self.env['hr.manual.time.log'].sudo()
        Limit = self.env['hrms.medical.limit'].sudo()
        for rec in self:
            if not rec.employee_id or not rec.year:
                rec.annual_limit = 0.0
                rec.remaining_preview = 0.0
                continue
            limit = Limit.get_limit_for(rec.employee_id, rec.year)
            in_system = sum(Log.search([
                ('employee_id', '=', rec.employee_id.id),
                ('is_medical', '=', True),
                ('expense_year', '=', rec.year),
                ('state', '=', 'อนุมัติ'),
            ]).mapped('amount'))
            rec.annual_limit = limit
            rec.remaining_preview = limit - rec.used_amount - in_system

    @api.constrains('year')
    def _check_year(self):
        for rec in self:
            _check_year_value(rec.year)

    @api.constrains('used_amount')
    def _check_used_amount(self):
        for rec in self:
            if rec.used_amount < 0:
                raise ValidationError('ยอดที่เบิกไปแล้วต้องไม่ติดลบ')

    @api.constrains('year', 'employee_id')
    def _check_unique(self):
        for rec in self:
            if self.sudo().search_count([
                ('year', '=', rec.year),
                ('employee_id', '=', rec.employee_id.id),
                ('id', '!=', rec.id),
            ]):
                raise ValidationError(
                    'บันทึกยอดเดิมของ %s ปี %s ไว้แล้ว — แก้ไขรายการเดิมแทนการสร้างใหม่\n'
                    'ถ้าสร้างซ้ำ ยอดจะถูกหักสองรอบ'
                    % (rec.employee_id.display_name, rec.year))

    @api.model
    def get_used_before(self, employee, year):
        if not employee:
            return 0.0
        rec = self.sudo().search([
            ('year', '=', year),
            ('employee_id', '=', employee.id),
        ], limit=1)
        return rec.used_amount if rec else 0.0
