# -*- coding: utf-8 -*-
"""เทมเพลตวันหยุดประจำปี

พอร์ตจาก Odoo 14 — เปลี่ยน unique(year) เป็น unique(year, company_id)
เพราะ Odoo 18 ใช้ DB เดียวหลายบริษัท แต่ละบริษัทประกาศวันหยุดของตัวเองได้
"""
from odoo import models, fields, api
from odoo.exceptions import UserError


class PayrollHoliday(models.Model):
    _name = 'payroll.holiday'
    _description = 'เทมเพลตวันหยุดประจำปี'
    _order = 'year desc'

    name = fields.Char(
        string='ชื่อเทมเพลต', compute='_compute_name', store=True, readonly=True)
    year = fields.Integer(
        string='ปี', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)
    line_ids = fields.One2many(
        'payroll.holiday.line', 'holiday_id', string='รายการวันหยุด')
    holiday_count = fields.Integer(
        string='จำนวนวันหยุด', compute='_compute_holiday_count')

    _sql_constraints = [
        ('year_company_uniq', 'unique(year, company_id)',
         'สร้างเทมเพลตวันหยุดได้เพียงหนึ่งรายการต่อปีต่อบริษัท'),
    ]

    @api.depends('year', 'company_id')
    def _compute_name(self):
        for rec in self:
            rec.name = f'วันหยุดประจำปี {rec.year}' if rec.year else False

    @api.depends('line_ids')
    def _compute_holiday_count(self):
        for rec in self:
            rec.holiday_count = len(rec.line_ids)

    def action_copy_from_previous_year(self):
        """คัดลอกวันหยุดจากปีก่อนหน้ามาเป็นตั้งต้น แล้วให้ผู้ใช้แก้วันที่เอง

        วันหยุดไทยส่วนใหญ่เลื่อนวัน — คัดลอกมาแล้วแก้เร็วกว่าพิมพ์ใหม่ทั้งปี
        """
        self.ensure_one()
        previous = self.search([
            ('year', '=', self.year - 1),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not previous:
            raise UserError('ไม่พบเทมเพลตวันหยุดของปี %s' % (self.year - 1))
        existing_dates = set(self.line_ids.mapped('date'))
        for line in previous.line_ids:
            new_date = line.date.replace(year=self.year)
            if new_date in existing_dates:
                continue
            self.env['payroll.holiday.line'].create({
                'holiday_id': self.id,
                'name': line.name,
                'date': new_date,
            })
        return True

    @api.model
    def get_holiday_dates(self, year, company_id=None):
        """คืน set ของวันหยุดในปีนั้น — payroll และ API ใช้ร่วมกัน"""
        company_id = company_id or self.env.company.id
        template = self.sudo().search([
            ('year', '=', year), ('company_id', '=', company_id)], limit=1)
        return set(template.line_ids.mapped('date'))

    @api.model
    def api_get_holidays(self, year=None, company_id=None):
        """เรียกจากแอป — คืน list ของ {date, name}"""
        year = year or fields.Date.context_today(self).year
        company_id = company_id or self.env.company.id
        template = self.sudo().search([
            ('year', '=', int(year)), ('company_id', '=', company_id)], limit=1)
        return [{
            'date': line.date.isoformat(),
            'name': line.name or '',
        } for line in template.line_ids.sorted('date')]


class PayrollHolidayLine(models.Model):
    _name = 'payroll.holiday.line'
    _description = 'รายการวันหยุด'
    _order = 'date'

    holiday_id = fields.Many2one(
        'payroll.holiday', string='เทมเพลตวันหยุด', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', related='holiday_id.company_id', store=True, readonly=True)
    name = fields.Char(string='ชื่อวันหยุด', required=True)
    date = fields.Date(string='วันที่', required=True)
    is_paid = fields.Boolean(
        string='เป็นวันหยุดได้รับค่าจ้าง', default=True,
        help='ติ๊กออกสำหรับวันหยุดที่ไม่จ่ายค่าจ้าง เช่น วันหยุดพิเศษที่ประกาศเพิ่ม')
