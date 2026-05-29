# -*- coding: utf-8 -*-
from odoo import models, fields, api


class NpdLoanCommissionPayout(models.Model):
    _name = 'npd.loan.commission.payout'
    _description = 'การจ่ายค่าคอม Sale (แยกรายงวด)'
    _order = 'payout_type desc, installment_id, sale_user_id'

    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', required=True, ondelete='cascade')
    sale_user_id = fields.Many2one('res.users', string='Sale', required=True)

    # ประเภท: หลัก หรือ รายงวด
    payout_type = fields.Selection([
        ('main', 'ค่าคอมหลัก'),
        ('installment', 'ค่าคอมรายงวด'),
    ], string='ประเภท', required=True, default='installment')

    # ผูกกับงวด (ถ้าเป็นรายงวด)
    installment_id = fields.Many2one('npd.loan.installment', string='งวดที่',
                                      domain="[('loan_id', '=', loan_id)]",
                                      ondelete='cascade')
    installment_no = fields.Integer(string='งวด', related='installment_id.installment_no', store=True)

    # จำนวนเงินค่าคอม
    commission_amount = fields.Float(string='ค่าคอม', digits=(12, 2))

    # ติ๊กจ่ายแล้ว
    is_paid = fields.Boolean(string='จ่ายแล้ว', default=False)

    # สถานะการจ่าย
    status = fields.Selection([
        ('pending', 'รอจ่าย'),
        ('paid', 'จ่ายแล้ว'),
    ], string='สถานะ', compute='_compute_status', store=True)

    payment_date = fields.Date(string='วันที่จ่าย')

    # สลิปการโอน (แสดงเป็นรูปภาพ)
    attachment = fields.Image(string='สลิปการโอน', max_width=1024, max_height=1024)

    note = fields.Text(string='หมายเหตุ')

    # Display name
    display_label = fields.Char(string='รายการ', compute='_compute_display_label')

    @api.depends('is_paid')
    def _compute_status(self):
        for rec in self:
            rec.status = 'paid' if rec.is_paid else 'pending'

    def _compute_display_label(self):
        for rec in self:
            if rec.payout_type == 'main':
                rec.display_label = 'ค่าคอมหลัก'
            else:
                rec.display_label = 'งวดที่ %s' % (rec.installment_no or '-')
