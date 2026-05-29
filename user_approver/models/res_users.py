# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ✅ ฟิลด์ผู้อนุมัติ
    is_approver = fields.Boolean(
        string='ผู้อนุมัติ',
        default=False,
        help='ติ๊กเพื่อกำหนดว่าผู้ใช้คนนี้เป็นผู้อนุมัติหรือไม่',
        tracking=True
    )

    # 📝 บันทึก log เมื่อมีการเปลี่ยนแปลง
    @api.model
    def create(self, vals):
        if vals.get('is_approver'):
            _logger.info(f"✅ Created new approver: {vals.get('name')}")
        return super(ResUsers, self).create(vals)

    def write(self, vals):
        if 'is_approver' in vals:
            for user in self:
                old_value = user.is_approver
                new_value = vals.get('is_approver')
                if old_value != new_value:
                    status = "เป็น" if new_value else "ไม่เป็น"
                    _logger.info(f"🔄 User {user.name} changed approver status: {status}ผู้อนุมัติ")
        return super(ResUsers, self).write(vals)
