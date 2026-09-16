# -*- coding: utf-8 -*-
"""สถานะตรวจสอบของเอกสารรายจ่าย - แยกจากสถานะหลัก (state) ของเอกสาร

ใช้ร่วมกันทั้ง 3 เมนู: บิลผู้ขาย / Avance Clear / การรับ
"""

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from .res_users import EXPENSE_REVIEW_GROUP

REVIEW_STATE_SELECTION = [
    ('waiting', 'รอตรวจสอบ'),
    ('checked', 'ตรวจสอบแล้ว'),
]


class NpdExpenseReviewMixin(models.AbstractModel):
    _name = 'npd.expense.review.mixin'
    _description = 'สถานะตรวจสอบเอกสารรายจ่าย'

    review_state = fields.Selection(
        REVIEW_STATE_SELECTION,
        string='สถานะตรวจสอบ',
        default='waiting',
        required=True,
        readonly=True,
        copy=False,
        index=True,
        tracking=True,
    )
    review_user_id = fields.Many2one(
        'res.users', string='ผู้ตรวจสอบ', readonly=True, copy=False)
    review_date = fields.Datetime(
        string='วันที่ตรวจสอบ', readonly=True, copy=False)

    def _npd_review_applicable(self):
        """เอกสารที่ใช้สถานะตรวจสอบได้ - แต่ละเมนูกรองเพิ่มเองได้"""
        return self

    def _npd_review_write(self, vals):
        if not self.env.user.has_group(EXPENSE_REVIEW_GROUP):
            raise AccessError(_('คุณไม่มีสิทธิ์เปลี่ยนสถานะตรวจสอบ '
                                'กรุณาติดต่อผู้ดูแลระบบให้เปิด "แสดงปุ่มตรวจสอบแล้ว"'))
        not_applicable = self - self._npd_review_applicable()
        if not_applicable:
            raise UserError(_('เอกสารต่อไปนี้ไม่อยู่ในเมนูที่ใช้สถานะตรวจสอบ: %s')
                            % ', '.join(not_applicable.mapped('display_name')))
        return self.write(vals)

    def action_review_checked(self):
        """ปุ่ม ตรวจสอบแล้ว"""
        records = self.filtered(lambda r: r.review_state != 'checked')
        records._npd_review_write({
            'review_state': 'checked',
            'review_user_id': self.env.user.id,
            'review_date': fields.Datetime.now(),
        })
        return True

    def action_review_waiting(self):
        """ปุ่ม รอตรวจสอบ (ย้อนกลับ)"""
        records = self.filtered(lambda r: r.review_state != 'waiting')
        records._npd_review_write({
            'review_state': 'waiting',
            'review_user_id': False,
            'review_date': False,
        })
        return True
