# -*- coding: utf-8 -*-
from odoo import models, fields

class NpdLoanDocument(models.Model):
    _name = 'npd.loan.document'
    _description = 'เอกสารแนบสินเชื่อ'
    _order = 'sequence, id'

    name = fields.Char(string='ชื่อเอกสาร', required=True)
    loan_id = fields.Many2one('npd.loan', string='สินเชื่อ', required=True, ondelete='cascade')
    sequence = fields.Integer(string='ลำดับ', default=10)
    
    document_type = fields.Selection([
        ('id_card', 'สำเนาบัตรประชาชน'),
        ('house_reg', 'สำเนาทะเบียนบ้าน'),
        ('vehicle_reg', 'สำเนาทะเบียนรถ'),
        ('income_cert', 'หนังสือรับรองรายได้'),
        ('bank_statement', 'Statement ธนาคาร'),
        ('contract', 'สัญญากู้'),
        ('guarantee', 'หนังสือค้ำประกัน'),
        ('photo', 'รูปถ่าย'),
        ('other', 'อื่นๆ'),
    ], string='ประเภทเอกสาร', required=True)
    
    attachment = fields.Binary(string='ไฟล์แนบ', required=True, attachment=True)
    attachment_name = fields.Char(string='ชื่อไฟล์')
    description = fields.Text(string='รายละเอียด')
    upload_date = fields.Date(string='วันที่อัพโหลด', default=fields.Date.today)
    uploaded_by = fields.Many2one('res.users', string='ผู้อัพโหลด', 
                                   default=lambda self: self.env.user)
