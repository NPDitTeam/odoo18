# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .account_payment import BYPASS_GROUP


class ResUsers(models.Model):
    _inherit = 'res.users'

    # อ่าน/เขียนจากสมาชิกของกลุ่มโดยตรง จึงตรงกับแท็บ Access Rights เสมอ
    allow_late_payment_post = fields.Boolean(
        string='รับชำระย้อนหลังที่เลยกำหนดได้ (ฝ่ายการเงิน)',
        compute='_compute_allow_late_payment_post',
        inverse='_inverse_allow_late_payment_post',
        help='ติ๊กเพื่อให้ผู้ใช้นี้ยืนยันใบรับชำระที่วันที่โอนตามสลิป '
             'เลยวันที่ 10 ของเดือนถัดไปแล้วได้',
    )

    @api.model
    def _get_late_post_bypass_group(self):
        return self.env.ref(BYPASS_GROUP, raise_if_not_found=False)

    @api.depends('groups_id')
    def _compute_allow_late_payment_post(self):
        group = self._get_late_post_bypass_group()
        for user in self:
            user.allow_late_payment_post = bool(group) and group in user.groups_id

    def _inverse_allow_late_payment_post(self):
        group = self._get_late_post_bypass_group()
        if not group:
            return
        for user in self:
            command = 4 if user.allow_late_payment_post else 3
            group.sudo().write({'users': [(command, user.id)]})
