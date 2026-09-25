# -*- coding: utf-8 -*-
"""บันทึกผลการซิงก์แต่ละรอบ

ช่วงรันคู่ขนาน ถ้าตัวเลขสองฝั่งไม่ตรงกันต้องตอบให้ได้ว่าเพราะอะไร
ใบบันทึกนี้จึงเก็บว่ารอบไหนดึงอะไรมาได้กี่แถว สร้างใหม่กี่แถว แก้กี่แถว
และแถวไหนพลาดเพราะอะไร เก็บข้อความผิดพลาดดิบไว้ด้วย ไม่ตัดทิ้ง
"""
from odoo import models, fields, api


class HrmsSyncLog(models.Model):
    _name = 'npd.hrms.sync.log'
    _description = 'ผลการซิงก์ข้อมูลจาก Odoo 14'
    _order = 'date_start desc, id desc'
    _rec_name = 'display_name'

    config_id = fields.Many2one('npd.hrms.sync.config', string='การเชื่อมต่อ',
                                ondelete='set null')
    date_start = fields.Datetime(string='เริ่มเมื่อ', required=True,
                                 default=lambda self: fields.Datetime.now())
    date_end = fields.Datetime(string='จบเมื่อ')
    duration = fields.Float(string='ใช้เวลา (วินาที)', compute='_compute_duration',
                            store=True)
    mode = fields.Selection([
        ('incremental', 'เฉพาะที่เปลี่ยน'),
        ('full', 'ทั้งหมด'),
    ], string='รูปแบบ', default='incremental', required=True)
    state = fields.Selection([
        ('running', 'กำลังทำงาน'),
        ('done', 'สำเร็จ'),
        ('partial', 'สำเร็จบางส่วน'),
        ('failed', 'ล้มเหลว'),
    ], string='สถานะ', default='running', required=True)

    fetched = fields.Integer(string='ดึงมา', default=0)
    created_count = fields.Integer(string='สร้างใหม่', default=0)
    updated_count = fields.Integer(string='แก้ไข', default=0)
    skipped_count = fields.Integer(string='ข้าม', default=0)
    error_count = fields.Integer(string='ผิดพลาด', default=0)

    note = fields.Text(string='สรุป')
    line_ids = fields.One2many('npd.hrms.sync.log.line', 'log_id',
                               string='รายหัวข้อ')

    display_name = fields.Char(compute='_compute_display_name', store=False)

    @api.depends('date_start', 'mode', 'state')
    def _compute_display_name(self):
        labels = dict(self._fields['state'].selection)
        for rec in self:
            stamp = fields.Datetime.context_timestamp(rec, rec.date_start) \
                if rec.date_start else False
            rec.display_name = '%s — %s' % (
                stamp.strftime('%d/%m/%Y %H:%M') if stamp else '-',
                labels.get(rec.state, rec.state))

    @api.depends('date_start', 'date_end')
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                rec.duration = (rec.date_end - rec.date_start).total_seconds()
            else:
                rec.duration = 0.0

    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'รายหัวข้อ',
            'res_model': 'npd.hrms.sync.log.line',
            'view_mode': 'list,form',
            'domain': [('log_id', '=', self.id)],
        }


class HrmsSyncLogLine(models.Model):
    _name = 'npd.hrms.sync.log.line'
    _description = 'ผลการซิงก์รายหัวข้อ'
    _order = 'sequence, id'

    log_id = fields.Many2one('npd.hrms.sync.log', string='รอบการซิงก์',
                             required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='ลำดับ', default=10)
    name = fields.Char(string='หัวข้อ', required=True)
    o14_model = fields.Char(string='โมเดลฝั่ง 14')
    o18_model = fields.Char(string='โมเดลฝั่ง 18')

    fetched = fields.Integer(string='ดึงมา', default=0)
    created_count = fields.Integer(string='สร้างใหม่', default=0)
    updated_count = fields.Integer(string='แก้ไข', default=0)
    skipped_count = fields.Integer(string='ข้าม', default=0)
    error_count = fields.Integer(string='ผิดพลาด', default=0)

    state = fields.Selection([
        ('done', 'สำเร็จ'),
        ('partial', 'สำเร็จบางส่วน'),
        ('failed', 'ล้มเหลว'),
        ('skipped', 'ปิดไว้'),
    ], string='สถานะ', default='done')
    message = fields.Text(string='รายละเอียด',
                          help='ถ้ามีแถวที่พลาด จะเก็บข้อความผิดพลาดดิบไว้ที่นี่')
