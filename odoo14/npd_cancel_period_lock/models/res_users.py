# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .cancel_lock_mixin import BYPASS_GROUP


class ResUsers(models.Model):
    _inherit = 'res.users'

    # อ่าน/เขียนจากสมาชิกของกลุ่มโดยตรง จึงตรงกับแท็บ Access Rights เสมอ
    allow_cancel_locked_period = fields.Boolean(
        string='ยกเลิกเอกสารเดือนก่อนหน้าได้ (ฝ่ายการเงิน)',
        compute='_compute_allow_cancel_locked_period',
        inverse='_inverse_allow_cancel_locked_period',
        help='ติ๊กเพื่อให้ผู้ใช้นี้ยกเลิก / รีเซ็ตเป็นแบบร่าง ใบแจ้งหนี้และใบรับชำระ '
             'ของเดือนก่อนหน้าได้ โดยไม่สนเงื่อนไขล็อกงวด',
    )

    @api.model
    def _get_cancel_lock_bypass_group(self):
        return self.env.ref(BYPASS_GROUP, raise_if_not_found=False)

    @api.depends('groups_id')
    def _compute_allow_cancel_locked_period(self):
        group = self._get_cancel_lock_bypass_group()
        for user in self:
            user.allow_cancel_locked_period = bool(group) and group in user.groups_id

    def _inverse_allow_cancel_locked_period(self):
        group = self._get_cancel_lock_bypass_group()
        if not group:
            return
        for user in self:
            command = 4 if user.allow_cancel_locked_period else 3
            group.sudo().write({'users': [(command, user.id)]})
