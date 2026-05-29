# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NpdLoanType(models.Model):
    _name = 'npd.loan.type'
    _description = 'ประเภทสินเชื่อ'
    _order = 'sequence, name'

    name = fields.Char(string='ชื่อประเภทสินเชื่อ', required=True)
    code = fields.Char(string='รหัส', required=True)
    sequence = fields.Integer(string='ลำดับ', default=10)
    active = fields.Boolean(string='ใช้งาน', default=True)
    description = fields.Text(string='รายละเอียด')
    
    # อัตราดอกเบี้ยปกติ
    interest_rate = fields.Float(string='อัตราดอกเบี้ย (%/เดือน)', digits=(5, 2))
    
    # อัตราดอกเบี้ยล่าช้า
    late_fee_rate = fields.Float(
        string='อัตราค่าปรับล่าช้า (%)', 
        digits=(5, 4), 
        default=0.1,
        help='อัตราค่าปรับที่คิดเพิ่มเมื่อชำระล่าช้า'
    )
    
    # ประเภทการคิดค่าปรับ
    late_fee_type = fields.Selection([
        ('daily', 'คิดเป็นรายวัน'),
        ('per_period', 'คิดเป็นรอบ'),
    ], string='วิธีคิดค่าปรับ', default='per_period',
       help='รายวัน: ค่าปรับ = ยอดค้าง x อัตรา% x จำนวนวัน\nรอบ: ค่าปรับ = ยอดค้าง x อัตรา% (คิดครั้งเดียวต่องวด)')
    
    max_amount = fields.Float(string='วงเงินสูงสุด')
    max_period = fields.Integer(string='ระยะเวลาสูงสุด (เดือน)')
    
    loan_ids = fields.One2many('npd.loan', 'loan_type_id', string='สินเชื่อ')
    loan_count = fields.Integer(string='จำนวนสินเชื่อ', compute='_compute_loan_count')

    @api.depends('loan_ids')
    def _compute_loan_count(self):
        for rec in self:
            rec.loan_count = len(rec.loan_ids)

    def action_view_loans(self):
        return {
            'name': 'สินเชื่อ',
            'type': 'ir.actions.act_window',
            'res_model': 'npd.loan',
            'view_mode': 'list,form',
            'domain': [('loan_type_id', '=', self.id)],
            'context': {'default_loan_type_id': self.id},
        }

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'รหัสประเภทสินเชื่อต้องไม่ซ้ำกัน!'),
    ]
