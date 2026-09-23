# -*- coding: utf-8 -*-
import mimetypes

from odoo import api, models, fields

# นามสกุลที่ถือว่าเป็น "รูป" แสดงตัวอย่างได้ (เอกสารอื่น เช่น PDF ให้ดาวน์โหลดตามเดิม)
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')

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

    is_image = fields.Boolean(
        string='เป็นไฟล์รูป', compute='_compute_is_image', store=True,
        help='ดูจากนามสกุลไฟล์ ใช้ตัดสินว่าจะแสดงรูปตัวอย่างให้หรือไม่')
    image_preview = fields.Binary(
        string='รูป', compute='_compute_image_preview',
        help='รูปตัวอย่างของไฟล์แนบ (เฉพาะไฟล์รูป) คลิกที่รูปเพื่อดูขนาดเต็ม')

    @api.depends('attachment_name')
    def _compute_is_image(self):
        for rec in self:
            name = (rec.attachment_name or '').lower()
            if name:
                rec.is_image = name.endswith(IMAGE_EXTENSIONS)
                continue
            # ไม่มีชื่อไฟล์ (นำเข้าข้อมูลเก่า) -> เดาจาก mimetype ของชื่อที่มี
            mimetype = mimetypes.guess_type(rec.name or '')[0] or ''
            rec.is_image = mimetype.startswith('image/')

    @api.depends('attachment', 'is_image')
    def _compute_image_preview(self):
        """คืนไฟล์เดิมเมื่อเป็นรูป — ไม่เก็บซ้ำ จึงไม่กินพื้นที่เพิ่ม

        ไฟล์ที่ไม่ใช่รูป (PDF/Excel) คืน False เพื่อให้ช่องรูปว่างแทนรูปเสีย
        """
        for rec in self:
            rec.image_preview = rec.attachment if rec.is_image else False
