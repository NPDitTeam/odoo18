# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools.misc import format_datetime

from .lock_fields import LOCK_DATE_FIELDS, LOCK_FIELD_LABELS, WIZARD_WRITE, lock_direction


class NpdAccountLockLog(models.Model):
    """ประวัติการเปลี่ยนวันล็อกงวด 1 แถวต่อ 1 ช่องที่เปลี่ยนจริง

    เขียนจาก res.company.write เท่านั้น จึงจับได้ทุกช่องทาง (หน้าจอนี้ ตัวช่วยปิดงบ AI-IT
    สคริปต์ shell งานตั้งเวลา) รวมถึงการสร้างข้อยกเว้นการล็อก ซึ่งปลดล็อกได้โดยไม่แตะวันล็อกของบริษัท
    ผู้ใช้ไม่มีสิทธิ์เขียน/ลบเลยใน ACL ปลอมแถวจากหน้าจอหรือ RPC ไม่ได้
    """
    _name = 'npd.account.lock.log'
    _description = 'ประวัติการล็อกงวดบัญชี'
    _order = 'change_datetime desc, id desc'
    _rec_name = 'field_name'

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True, readonly=True,
    )
    user_id = fields.Many2one('res.users', string='ผู้แก้ไข', required=True, readonly=True)
    change_datetime = fields.Datetime(
        string='เวลาที่แก้', required=True, readonly=True, default=fields.Datetime.now,
    )
    field_name = fields.Selection(
        [(f, LOCK_FIELD_LABELS[f]) for f in LOCK_DATE_FIELDS],
        string='ชนิดล็อก', required=True, readonly=True,
    )
    old_date = fields.Date(string='ค่าเดิม', readonly=True, help='ว่าง = ไม่ล็อก')
    new_date = fields.Date(string='ค่าใหม่', readonly=True, help='ว่าง = ไม่ล็อก')
    direction = fields.Selection(
        [('lock', 'ล็อกเพิ่ม / เลื่อนไปข้างหน้า'), ('unlock', 'ปลดล็อก / ถอยหลัง')],
        string='ทิศทาง', required=True, readonly=True,
    )
    source = fields.Selection(
        [
            ('wizard', 'หน้าจอล็อกงวดบัญชี'),
            ('exception', 'ข้อยกเว้นการล็อก (ปลดให้บางคน/ชั่วคราว)'),
            ('other', 'ช่องทางอื่น (AI-IT / สคริปต์ / ระบบ)'),
        ],
        string='ช่องทาง', required=True, readonly=True, default='other',
    )
    note = fields.Text(string='เหตุผล / หมายเหตุ', readonly=True)

    @api.model
    def _log_lock_changes(self, companies, before, fnames):
        """เทียบค่าก่อน/หลังเขียน ไม่ใช่เทียบกับ vals

        เขียนค่าเดิมซ้ำ (เช่น AI-IT ย้อนกลับเป็นค่าเดียวกัน) จะไม่เกิดแถวขยะ
        ผู้แก้ = env.user ซึ่งภายใต้ sudo ยังเป็นผู้ใช้จริงที่สั่ง ไม่ใช่ OdooBot
        "มาจากหน้าจอ" เชื่อเฉพาะป้ายที่ action_apply ตั้งเอง (WIZARD_WRITE) ไม่เชื่อ context
        ส่วนหมายเหตุของช่องทางอื่นรับจาก context npd_lock_note ได้ เพราะไม่ได้อ้างว่าผ่านการตรวจของหน้าจอ
        """
        wizard = WIZARD_WRITE.get()
        if wizard is not None:
            source, note = 'wizard', wizard.get('note') or False
        else:
            source, note = 'other', self.env.context.get('npd_lock_note') or False
        vals_list = []
        for company in companies:
            old_values = before.get(company.id, {})
            for fname in fnames:
                old = old_values.get(fname) or False
                new = company[fname] or False
                if old == new:
                    continue
                vals_list.append({
                    'company_id': company.id,
                    'user_id': self.env.user.id,
                    'field_name': fname,
                    'old_date': old,
                    'new_date': new,
                    'direction': lock_direction(old, new),
                    'source': source,
                    'note': note,
                })
        if vals_list:
            self.sudo().create(vals_list)

    @api.model
    def _log_lock_exceptions(self, exceptions):
        """ข้อยกเว้นการล็อกลดวันล็อกที่มีผลจริงลงได้ (ถึงขั้นปลดหมด) โดยวันล็อกบนบริษัทไม่เปลี่ยน
        จึงต้องเก็บแยก ไม่งั้นประวัติและหน้าสถานะจะบอกว่ายังล็อกอยู่ทั้งที่มีคนแก้เอกสารในช่วงนั้นได้
        """
        vals_list = []
        for exception in exceptions.sudo():
            target = exception.user_id.display_name if exception.user_id else 'ทุกคน'
            until = (
                format_datetime(self.env, exception.end_datetime) if exception.end_datetime else 'ไม่มีกำหนด'
            )
            old = exception.company_lock_date or False
            new = exception.lock_date or False
            vals_list.append({
                'company_id': exception.company_id.id,
                'user_id': self.env.user.id,
                'field_name': exception.lock_date_field,
                'old_date': old,
                'new_date': new,
                'direction': lock_direction(old, new),
                'source': 'exception',
                'note': 'ข้อยกเว้นสำหรับ %s ถึง %s: %s' % (target, until, exception.reason or ''),
            })
        if vals_list:
            self.sudo().create(vals_list)
