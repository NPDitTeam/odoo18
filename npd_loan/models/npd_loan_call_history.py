# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class NpdLoanCallHistory(models.Model):
    _name = 'npd.loan.call.history'
    _description = 'ประวัติการโทร'
    _order = 'call_datetime desc'

    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', required=True, ondelete='cascade')
    customer_id = fields.Many2one('res.partner', string='ลูกค้า', related='loan_id.customer_id', store=True)
    
    # ข้อมูลการโทร
    phone_number = fields.Char(string='เบอร์ที่โทร')
    call_datetime = fields.Datetime(string='วันเวลาที่โทร', default=fields.Datetime.now)
    call_duration = fields.Integer(string='ระยะเวลา (วินาที)', default=0)
    call_duration_display = fields.Char(string='ระยะเวลา', compute='_compute_duration_display')
    
    # งวดที่เลือก
    installment_id = fields.Many2one('npd.loan.installment', string='งวดที่ติดตาม')
    installment_no = fields.Integer(string='งวดที่', related='installment_id.installment_no', store=True)
    amount_due = fields.Float(string='ยอดที่ติดตาม', digits=(12, 2))
    
    # ผลการโทร
    call_status = fields.Selection([
        ('answered', 'รับสาย'),
        ('no_answer', 'ไม่รับสาย'),
        ('busy', 'สายไม่ว่าง'),
        ('wrong_number', 'เบอร์ผิด'),
        ('promise_pay', 'สัญญาจะชำระ'),
        ('refuse_pay', 'ปฏิเสธชำระ'),
        ('other', 'อื่นๆ'),
    ], string='สถานะการโทร', required=True)
    
    note = fields.Text(string='หมายเหตุ', required=True)
    
    # ผู้โทร
    caller_id = fields.Many2one('res.users', string='ผู้โทร', default=lambda self: self.env.user)

    @api.depends('call_duration')
    def _compute_duration_display(self):
        for rec in self:
            mins, secs = divmod(rec.call_duration, 60)
            rec.call_duration_display = '%d:%02d นาที' % (mins, secs)
