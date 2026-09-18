# -*- coding: utf-8 -*-
"""หัวข้อปัญหาที่ให้ "ตัวช่วย AI-IT" แก้ให้

แต่ละหัวข้อผูกกับ code ตัวหนึ่ง และ code นั้นต้องมี handler รองรับใน
ai_it_session.py หัวข้อที่ยังไม่มี handler จะขึ้นข้อความว่ายังไม่เปิดให้บริการ
(ไม่ทำให้ระบบพัง) เพื่อให้เพิ่มหัวข้อถัดไปได้ทีละหัวข้อ
"""
from odoo import api, fields, models

# code ของหัวข้อที่มี handler พร้อมใช้งานแล้ว
IMPLEMENTED_CODES = ('stock_not_enough', 'invoice_date_fix', 'return_date_fix',
                     'rental_status_fix', 'vat_round_fix', 'expense_check',
                     'closing_help')


class NpdAiItTopic(models.Model):
    _name = 'npd.ai.it.topic'
    _description = 'ตัวช่วย AI-IT : หัวข้อปัญหา'
    _order = 'sequence, id'

    name = fields.Char(string='หัวข้อ', required=True, translate=False)
    code = fields.Char(
        string='รหัสหัวข้อ', required=True,
        help='รหัสอ้างอิงที่ผูกกับขั้นตอนการทำงานในโค้ด เช่น stock_not_enough',
    )
    sequence = fields.Integer(string='ลำดับ', default=10)
    description = fields.Char(string='คำอธิบายสั้น')
    intro_message = fields.Text(
        string='ข้อความเริ่มบทสนทนา',
        help='ข้อความแรกที่ตัวช่วย AI-IT จะทักในแชทเมื่อพนักงานเลือกหัวข้อนี้',
    )
    active = fields.Boolean(string='เปิดใช้งาน', default=True)
    group_ids = fields.Many2many(
        'res.groups', 'npd_ai_it_topic_group_rel', 'topic_id', 'group_id',
        string='จำกัดเฉพาะกลุ่ม',
        help='ถ้าเว้นว่าง = พนักงานภายในทุกคนใช้ได้',
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'รหัสหัวข้อต้องไม่ซ้ำกัน'),
    ]

    def _is_available_for_user(self, user):
        self.ensure_one()
        if not self.group_ids:
            return True
        return bool(self.group_ids & user.groups_id)

    @api.model
    def get_available_topics(self):
        """ใช้โดยแท็บ "ตัวช่วย AI-IT" ในเมนูสนทนา (เรียกผ่าน RPC จาก JS)"""
        user = self.env.user
        topics = self.sudo().search([])
        result = []
        index = 0
        for topic in topics:
            if not topic._is_available_for_user(user):
                continue
            index += 1
            result.append({
                'id': topic.id,
                'index': index,
                'code': topic.code,
                'name': topic.name or '',
                'description': topic.description or '',
                'is_ready': topic.code in IMPLEMENTED_CODES,
            })
        return result
