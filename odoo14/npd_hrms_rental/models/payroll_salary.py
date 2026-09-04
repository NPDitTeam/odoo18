# -*- coding: utf-8 -*-
"""แสดงที่มาของค่าเที่ยว/เบี้ยเลี้ยงคนขับในสลิป

ตัวคำนวณอยู่ใน ``npd_hrms_payroll`` แล้ว (``_fetch_driver_allowance``)
โมดูลนี้เพิ่มการ "ตรวจสอบย้อนกลับ" — ให้ฝ่ายบุคคลเปิดดูได้ว่ายอดนี้
มาจากงานขนส่งใบไหนบ้าง ซึ่งเป็นคำถามที่เกิดขึ้นทุกเดือน
"""
from odoo import models, fields, api


class PayrollSalaryRental(models.Model):
    _inherit = 'payroll.salary'

    driver_id = fields.Many2one(
        'vehicle.driver', related='employee_id.driver_id',
        string='คนขับ', store=True, readonly=True)
    booking_ids = fields.Many2many(
        'vehicle.booking', string='งานขนส่งในรอบนี้',
        compute='_compute_booking_ids')
    booking_count = fields.Integer(
        string='จำนวนงานในรอบ', compute='_compute_booking_ids')

    @api.depends('employee_id', 'month', 'year', 'cutoff_day')
    def _compute_booking_ids(self):
        Booking = self.env['vehicle.booking'].sudo()
        for rec in self:
            rec.booking_ids = False
            rec.booking_count = 0
            if not rec.driver_id or not rec.month or not rec.year:
                continue
            date_from, date_to = rec._cycle_window()
            if not date_from:
                continue
            bookings = Booking.search([
                ('driver_id', '=', rec.driver_id.id),
                ('state', '=', 'done'),
                ('delivery_date', '>=', date_from),
                ('delivery_date', '<=', date_to),
            ])
            rec.booking_ids = [(6, 0, bookings.ids)]
            rec.booking_count = len(bookings)

    def action_view_cycle_bookings(self):
        """เปิดงานขนส่งที่เป็นที่มาของค่าเที่ยวในรอบนี้"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'งานขนส่งในรอบ %s/%s' % (self.month, self.year),
            'res_model': 'vehicle.booking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.booking_ids.ids)],
        }
