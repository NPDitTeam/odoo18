# -*- coding: utf-8 -*-
u"""ประวัติการแก้ไขที่ทำผ่าน "ตัวช่วย AI-IT"

แยกจาก npd.ai.it.session โดยตั้งใจ — session คือ "บทสนทนา" ซึ่งมีทั้งที่คุยค้าง
ยกเลิกกลางทาง และคุยเล่น ส่วนตารางนี้บันทึกเฉพาะ "งานที่ทำสำเร็จจริง" เท่านั้น
เพื่อให้ฝ่ายบัญชีเปิดดูย้อนหลังได้ว่า ใคร แก้อะไร ของสาขาไหน เมื่อไร เพราะอะไร
"""
from odoo import api, fields, models

ACTION_TYPES = [
    ('stock_topup', u'เติมสต๊อกให้พอตัด'),
    ('stock_location', u'สร้าง/ผูกคลังของสาขา'),
    ('stock_cut', u'ตัดสต๊อกให้'),
    ('invoice_date', u'แก้วันที่ใบแจ้งหนี้'),
    ('invoice_cancel', u'ยกเลิกใบแจ้งหนี้'),
    ('return_date', u'แก้วันที่คืนสินค้า'),
    ('rental_status', u'แก้สถานะการเช่า'),
    ('invoice_vat_round', u'แก้การปัดเศษ VAT ใบแจ้งหนี้'),
]


class NpdAiItHistory(models.Model):
    _name = 'npd.ai.it.history'
    _description = u'ตัวช่วย AI-IT : ประวัติการแก้ไข'
    _order = 'date desc, id desc'
    _rec_name = 'document_ref'

    date = fields.Datetime(
        string=u'วันที่แก้', required=True, index=True,
        default=fields.Datetime.now,
    )
    action_type = fields.Selection(
        ACTION_TYPES, string=u'ประเภทการแก้', required=True, index=True)
    topic_id = fields.Many2one('npd.ai.it.topic', string=u'หัวข้อ')
    user_id = fields.Many2one(
        'res.users', string=u'ผู้แก้', required=True, index=True,
        default=lambda self: self.env.user)
    branch_id = fields.Many2one('res.branch', string=u'สาขา', index=True)
    session_id = fields.Many2one(
        'npd.ai.it.session', string=u'บทสนทนา', ondelete='set null')

    res_model = fields.Char(string=u'โมเดลเอกสาร')
    res_id = fields.Integer(string=u'ไอดีเอกสาร')
    document_ref = fields.Char(string=u'เอกสาร', index=True)

    note = fields.Char(string=u'หมายเหตุ (แก้เพราะอะไร)')
    detail = fields.Text(string=u'รายละเอียดสิ่งที่ทำ')

    @api.depends('action_type', 'document_ref')
    def _compute_display_name(self):
        labels = dict(ACTION_TYPES)
        for record in self:
            label = labels.get(record.action_type, record.action_type or '')
            if record.document_ref:
                label = '%s — %s' % (record.document_ref, label)
            record.display_name = label

    def action_open_document(self):
        """เปิดเอกสารต้นทางจากบรรทัดประวัติ"""
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        if self.res_model not in self.env:
            return False
        record = self.env[self.res_model].browse(self.res_id)
        if not record.exists():
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def log(self, action_type, detail, session=None, note=False,
            res_model=None, res_id=None, document_ref=None,
            user=None, branch=None):
        """บันทึกหนึ่งบรรทัดประวัติ (ใช้ sudo เพราะพนักงานไม่มีสิทธิ์เขียนเอง)"""
        session = session or self.env['npd.ai.it.session']
        values = {
            'action_type': action_type,
            'detail': detail,
            'note': note or (session.change_note if session else False),
            'topic_id': session.topic_id.id if session else False,
            'session_id': session.id if session else False,
            'user_id': (user or (session.user_id if session else False)
                        or self.env.user).id,
            'branch_id': (branch or (session.branch_id if session else False)).id
            if (branch or (session.branch_id if session else False)) else False,
            'res_model': res_model or (session.document_model if session else False),
            'res_id': res_id or (session.document_id if session else False),
            'document_ref': document_ref or (session.document_ref if session else False),
        }
        return self.sudo().create(values)
