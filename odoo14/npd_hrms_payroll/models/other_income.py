# -*- coding: utf-8 -*-
"""เงินได้อื่นๆ — รายการจ่ายเพิ่มนอกเหนือจากเงินเดือนประจำ

พอร์ตจาก Odoo 14 โดยคงหลักการเดิม: ยอดจะเข้าสลิปก็ต่อเมื่อ
  1. รายการถูก "ยืนยัน" แล้ว และ
  2. วันที่จ่ายเงินของบรรทัดอยู่ใน "รอบตัดเงินเดือน" ของสลิปนั้น
     (ไม่ใช่เดือนปฏิทิน — ดูรอบ 25–24)
"""
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OtherIncome(models.Model):
    _name = 'other.income'
    _description = 'เงินได้อื่นๆ'
    _inherit = ['mail.thread']
    _order = 'create_date desc'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True, ondelete='restrict')
    employee_code = fields.Char(
        related='employee_id.employee_code', store=True, readonly=True, index=True)
    firstname = fields.Char(related='employee_id.firstname', store=True, readonly=True)
    lastname = fields.Char(related='employee_id.lastname', store=True, readonly=True)
    position_id = fields.Many2one(
        'hr.position.custom', related='employee_id.position_id',
        store=True, readonly=True)
    department_id = fields.Many2one(
        'hr.department.custom', related='employee_id.department_id',
        store=True, readonly=True)
    branch_id = fields.Many2one(
        'res.branch', related='employee_id.branch_id', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', related='employee_id.company_id', store=True, readonly=True)

    line_ids = fields.One2many(
        'other.income.line', 'other_income_id', string='รายการ')
    total_amount = fields.Float(
        string='รวมเป็นเงิน', compute='_compute_total_amount', store=True)
    state = fields.Selection([
        ('draft', 'ร่าง'),
        ('confirmed', 'ยืนยันแล้ว'),
    ], string='สถานะ', default='draft', required=True, tracking=True)
    note = fields.Text(string='หมายเหตุเพิ่มเติม')

    @api.depends('line_ids.amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('amount'))

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError('กรุณาเพิ่มรายการก่อนยืนยัน')
            rec.state = 'confirmed'
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    # ------------------------------------------------------------------
    @api.model
    def get_total_for_cycle(self, employee, date_from, date_to, payment_date=None):
        """ยอดรวมเงินได้อื่นๆ ที่ต้องจ่ายในรอบนี้

        ยึด ``payment_date`` ของแต่ละบรรทัดเทียบกับช่วงรอบตัด
        (Odoo 14 เคยเทียบกับ "เดือนของ payment_date บนสลิป" ซึ่งพลาดรายการ
        ที่จ่ายคาบรอยต่อรอบ)
        """
        if not employee:
            return 0.0
        lines = self.env['other.income.line'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'confirmed'),
            ('payment_date', '>=', date_from),
            ('payment_date', '<=', date_to),
        ])
        return sum(lines.mapped('amount'))

    @api.model
    def get_lines_for_cycle(self, employee, date_from, date_to):
        """บรรทัดที่เข้าเงื่อนไข — ใช้แสดงรายละเอียดในสลิป"""
        if not employee:
            return self.env['other.income.line']
        return self.env['other.income.line'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'confirmed'),
            ('payment_date', '>=', date_from),
            ('payment_date', '<=', date_to),
        ])


class OtherIncomeLine(models.Model):
    _name = 'other.income.line'
    _description = 'รายการเงินได้อื่นๆ'
    _order = 'payment_date desc, id desc'

    other_income_id = fields.Many2one(
        'other.income', string='เงินได้อื่นๆ', required=True, ondelete='cascade')
    employee_id = fields.Many2one(
        'employee.salary', related='other_income_id.employee_id',
        store=True, readonly=True, index=True)
    company_id = fields.Many2one(
        'res.company', related='other_income_id.company_id',
        store=True, readonly=True)
    state = fields.Selection(
        related='other_income_id.state', store=True, readonly=True, index=True)
    note = fields.Char(string='รายการ', required=True)
    amount = fields.Float(string='จำนวนเงิน', required=True)
    payment_date = fields.Date(
        string='วันที่จ่ายเงิน', required=True, index=True,
        default=fields.Date.context_today,
        help='ระบบใช้วันที่นี้ตัดสินว่ายอดเข้าสลิปรอบไหน')
    attachment = fields.Binary(string='ไฟล์แนบ', attachment=True)
    attachment_filename = fields.Char(string='ชื่อไฟล์แนบ')
