# -*- coding: utf-8 -*-
u"""สมุดบันทึก "สิ่งที่ AI ลงมือแก้ให้" ในงานปิดงบ -- ถอยกลับได้ทีละรายการ

ทำไมต้องมีตารางนี้แยกจาก npd.ai.it.history
    history เก็บไว้ "ดูย้อนหลัง" ว่าใครทำอะไร แต่ถอยกลับไม่ได้
    ตารางนี้เก็บ "ค่าก่อนแก้" ไว้ด้วย จึงกดถอยคืนได้จริง ทั้งทีละรายการ
    และถอยทั้งชุดที่ทำพร้อมกัน (batch เดียวกัน)

รองรับการถอย 2 แบบ
    write  -> เขียนค่าเดิมกลับเข้าฟิลด์
    create -> ลบระเบียนที่เพิ่งสร้าง

ข้อจำกัดที่ตั้งใจ: ตารางนี้ใช้กับ "งานตั้งค่า" เท่านั้น ไม่ได้ออกแบบมาเพื่อ
ถอยรายการบัญชี (ใบปิดบัญชีมีปุ่ม Cancel ของตัวเองอยู่แล้ว ซึ่งถอยได้ถูกต้องกว่า)
"""
import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

FIX_KINDS = [
    ('write', u'แก้ค่าในฟิลด์'),
    ('create', u'สร้างระเบียนใหม่'),
]


class NpdAiItClosingFix(models.Model):
    _name = 'npd.ai.it.closing.fix'
    _description = u'ตัวช่วย AI-IT : สิ่งที่ AI แก้ให้ในงานปิดงบ (ถอยกลับได้)'
    _order = 'id desc'

    date = fields.Datetime(string=u'เวลา', required=True, index=True,
                           default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string=u'ผู้สั่ง', required=True, index=True,
                              default=lambda self: self.env.user)
    session_id = fields.Many2one('npd.ai.it.session', string=u'บทสนทนา', ondelete='set null')
    batch = fields.Char(string=u'ชุดที่ทำพร้อมกัน', index=True,
                        help=u'ใช้จัดกลุ่มเวลากด "ถอยทั้งหมด" ของการสั่งครั้งเดียว')

    company_id = fields.Many2one('res.company', string=u'บริษัท', index=True)
    year = fields.Integer(string=u'ปีที่ปิด', index=True)
    action = fields.Char(string=u'งานที่ทำ', required=True, index=True)
    title = fields.Char(string=u'รายละเอียด', required=True)

    kind = fields.Selection(FIX_KINDS, string=u'ชนิดการแก้', required=True)
    res_model = fields.Char(string=u'โมเดล', required=True)
    res_id = fields.Integer(string=u'ไอดีระเบียน', required=True)
    field_name = fields.Char(string=u'ฟิลด์')
    old_value = fields.Text(string=u'ค่าก่อนแก้ (JSON)')
    new_value = fields.Text(string=u'ค่าหลังแก้ (JSON)')

    state = fields.Selection([('done', u'ทำแล้ว'), ('undone', u'ถอยกลับแล้ว')],
                             string=u'สถานะ', default='done', required=True, index=True)
    undo_note = fields.Char(string=u'หมายเหตุตอนถอย')

    # ------------------------------------------------------------------
    @api.model
    def log_write(self, record, field_name, old_value, new_value, action, title,
                  batch=None, session=None, year=False):
        u"""บันทึกการแก้ค่าในฟิลด์ (เก็บค่าเดิมไว้ถอย)"""
        return self.sudo().create({
            'action': action, 'title': title, 'kind': 'write',
            'res_model': record._name, 'res_id': record.id, 'field_name': field_name,
            'old_value': json.dumps(old_value, ensure_ascii=False, default=str),
            'new_value': json.dumps(new_value, ensure_ascii=False, default=str),
            'company_id': getattr(record, 'company_id', False) and record.company_id.id
                          or (record._name == 'res.company' and record.id) or False,
            'year': year or 0,
            'batch': batch or '',
            'session_id': session.id if session else False,
            'user_id': self.env.user.id,
        })

    @api.model
    def log_create(self, record, action, title, batch=None, session=None, year=False):
        u"""บันทึกการสร้างระเบียนใหม่ (ถอย = ลบทิ้ง)"""
        return self.sudo().create({
            'action': action, 'title': title, 'kind': 'create',
            'res_model': record._name, 'res_id': record.id,
            'company_id': getattr(record, 'company_id', False) and record.company_id.id or False,
            'year': year or 0,
            'batch': batch or '',
            'session_id': session.id if session else False,
            'user_id': self.env.user.id,
        })

    # ------------------------------------------------------------------
    def action_undo(self):
        u"""ถอยกลับรายการนี้ คืน (สำเร็จกี่รายการ, [ข้อความที่ถอยไม่ได้])

        ถอยทีละรายการอิสระต่อกัน รายการไหนถอยไม่ได้จะข้ามแล้วรายงาน
        ไม่ใช่ล้มทั้งชุด
        """
        done, problems = 0, []
        for fix in self:
            if fix.state == 'undone':
                problems.append(u'%s ถอยไปแล้ว' % fix.title)
                continue
            if fix.res_model not in self.env:
                problems.append(u'%s ไม่มีโมเดล %s ในฐานนี้' % (fix.title, fix.res_model))
                continue
            record = self.env[fix.res_model].sudo().browse(fix.res_id)
            if not record.exists():
                fix.sudo().write({'state': 'undone',
                                  'undo_note': u'ระเบียนถูกลบไปแล้ว ถือว่าถอยแล้ว'})
                done += 1
                continue
            try:
                with self.env.cr.savepoint():
                    if fix.kind == 'write':
                        old = json.loads(fix.old_value or 'null')
                        record.write({fix.field_name: old})
                        note = u'คืนค่าเดิม %s' % (old if old not in (None, False) else u'ว่าง')
                    else:
                        record.unlink()
                        note = u'ลบระเบียนที่สร้างไว้'
                    fix.sudo().write({'state': 'undone', 'undo_note': note})
                    done += 1
            except Exception as exc:  # noqa: BLE001 - รายการเดียวพังต้องไม่ล้มทั้งชุด
                _logger.warning(u'ช่วยปิดงบ: ถอย %s ไม่สำเร็จ (%s)', fix.title, exc)
                problems.append(u'%s — %s' % (fix.title, str(exc)[:90]))
        return done, problems

    def name_get(self):
        return [(f.id, u'%s — %s' % (f.title or f.action, u'ถอยแล้ว'
                                     if f.state == 'undone' else u'ทำแล้ว')) for f in self]
