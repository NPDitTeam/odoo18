# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class LoanCallWizard(models.TransientModel):
    _name = 'npd.loan.call.wizard'
    _description = 'โทรติดตาม'

    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', required=True)
    customer_name = fields.Char(string='ชื่อลูกค้า', related='loan_id.customer_name')
    
    # เบอร์โทร (ใช้ mobile ถ้ามี ไม่งั้นใช้ phone)
    phone_number = fields.Char(string='เบอร์โทร', compute='_compute_phone', store=True)
    clean_phone = fields.Char(string='เบอร์โทร (สากล)', compute='_compute_phone', store=True)
    
    # ข้อมูลสินเชื่อ
    loan_amount = fields.Float(string='เงินต้น', related='loan_id.loan_amount')
    current_remaining = fields.Float(string='เงินต้นคงเหลือ', related='loan_id.current_remaining_principal')
    total_collected = fields.Float(string='เก็บได้รวม', related='loan_id.actual_collected')
    
    # เลือกงวด
    installment_id = fields.Many2one('npd.loan.installment', string='งวดที่ติดตาม',
                                      domain="[('loan_id', '=', loan_id)]")
    
    # ข้อมูลงวดที่เลือก
    installment_due_date = fields.Date(string='วันครบกำหนด', compute='_compute_installment_info')
    installment_paid_date = fields.Date(string='วันที่ชำระ', compute='_compute_installment_info')
    installment_overdue_days = fields.Integer(string='วันเกิน', compute='_compute_installment_info')
    installment_late_fee = fields.Float(string='ค่าปรับ', compute='_compute_installment_info')
    installment_minimum = fields.Float(string='ชำระขั้นต่ำ', compute='_compute_installment_info')
    installment_amount = fields.Float(string='ยอดงวด', compute='_compute_installment_info')
    installment_state = fields.Selection([
        ('pending', 'รอชำระ'),
        ('paid', 'ชำระแล้ว'),
        ('overdue', 'เกินกำหนด'),
    ], string='สถานะงวด', compute='_compute_installment_info')
    
    # สถานะการโทร
    is_calling = fields.Boolean(string='กำลังโทร', default=False)
    call_start_time = fields.Datetime(string='เวลาเริ่มโทร')
    
    # ผลการโทร (บังคับเมื่อจบงาน)
    call_status = fields.Selection([
        ('answered', 'รับสาย'),
        ('no_answer', 'ไม่รับสาย'),
        ('busy', 'สายไม่ว่าง'),
        ('wrong_number', 'เบอร์ผิด'),
        ('promise_pay', 'สัญญาจะชำระ'),
        ('refuse_pay', 'ปฏิเสธชำระ'),
        ('other', 'อื่นๆ'),
    ], string='สถานะการโทร')
    
    note = fields.Text(string='หมายเหตุ')

    @api.depends('loan_id', 'loan_id.mobile', 'loan_id.phone')
    def _compute_phone(self):
        for rec in self:
            if rec.loan_id:
                phone = rec.loan_id.mobile or rec.loan_id.phone or ''
                rec.phone_number = phone
                # Clean phone
                clean = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('.', '')
                if clean.startswith('0'):
                    clean = '+66' + clean[1:]
                elif clean and not clean.startswith('+'):
                    clean = '+66' + clean
                rec.clean_phone = clean
            else:
                rec.phone_number = ''
                rec.clean_phone = ''

    @api.depends('installment_id')
    def _compute_installment_info(self):
        for rec in self:
            if rec.installment_id:
                inst = rec.installment_id
                rec.installment_due_date = inst.due_date
                rec.installment_paid_date = inst.paid_date
                rec.installment_overdue_days = inst.overdue_days
                rec.installment_late_fee = inst.late_fee
                rec.installment_minimum = inst.minimum_payment
                rec.installment_amount = inst.actual_payment or inst.minimum_payment
                rec.installment_state = inst.state
            else:
                rec.installment_due_date = False
                rec.installment_paid_date = False
                rec.installment_overdue_days = 0
                rec.installment_late_fee = 0
                rec.installment_minimum = 0
                rec.installment_amount = 0
                rec.installment_state = False

    def action_start_call(self):
        """กดเริ่มจับเวลา - เปิด phone link และ reload wizard"""
        self.ensure_one()
        
        if not self.phone_number:
            raise ValidationError(_('ไม่มีเบอร์โทร'))
        
        # บันทึกเวลาเริ่มโทร
        self.write({
            'is_calling': True,
            'call_start_time': fields.Datetime.now(),
        })
        
        # เรียก client action เพื่อเปิด phone link และ reload wizard
        return {
            'type': 'ir.actions.client',
            'tag': 'npd_loan_make_call',
            'params': {
                'phone': self.clean_phone or self.phone_number,
                'wizard_id': self.id,
            }
        }

    def action_end_call(self):
        """จบการโทร - บันทึกประวัติ"""
        self.ensure_one()
        
        if not self.call_status:
            raise ValidationError(_('กรุณาเลือกสถานะการโทร'))
        
        if not self.note:
            raise ValidationError(_('กรุณาใส่หมายเหตุ'))
        
        # คำนวณระยะเวลา
        duration = 0
        if self.call_start_time:
            delta = fields.Datetime.now() - self.call_start_time
            duration = int(delta.total_seconds())
        
        # บันทึกประวัติการโทร
        self.env['npd.loan.call.history'].create({
            'loan_id': self.loan_id.id,
            'phone_number': self.phone_number,
            'call_datetime': self.call_start_time or fields.Datetime.now(),
            'call_duration': duration,
            'installment_id': self.installment_id.id if self.installment_id else False,
            'amount_due': self.installment_amount,
            'call_status': self.call_status,
            'note': self.note,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'บันทึกสำเร็จ',
                'message': 'บันทึกประวัติการโทรเรียบร้อย (ระยะเวลา %d วินาที)' % duration,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
