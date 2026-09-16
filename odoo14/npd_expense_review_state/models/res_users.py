# -*- coding: utf-8 -*-

from odoo import api, fields, models

EXPENSE_REVIEW_GROUP = 'npd_expense_review_state.group_expense_review'


class ResUsers(models.Model):
    _inherit = 'res.users'

    # อ่าน/เขียนจากสมาชิกของกลุ่มโดยตรง จึงตรงกับแท็บ Access Rights เสมอ
    show_expense_review_button = fields.Boolean(
        string='แสดงปุ่มตรวจสอบแล้ว (เอกสารรายจ่าย)',
        compute='_compute_show_expense_review_button',
        inverse='_inverse_show_expense_review_button',
        help='ติ๊กเพื่อให้ผู้ใช้นี้เห็นและกดปุ่ม "ตรวจสอบแล้ว" / "รอตรวจสอบ" '
             'บนบิลผู้ขาย / Avance Clear / การรับ ได้',
    )

    @api.model
    def _get_expense_review_group(self):
        return self.env.ref(EXPENSE_REVIEW_GROUP, raise_if_not_found=False)

    @api.depends('groups_id')
    def _compute_show_expense_review_button(self):
        group = self._get_expense_review_group()
        for user in self:
            user.show_expense_review_button = bool(group) and group in user.groups_id

    def _inverse_show_expense_review_button(self):
        group = self._get_expense_review_group()
        if not group:
            return
        for user in self:
            command = 4 if user.show_expense_review_button else 3
            group.sudo().write({'users': [(command, user.id)]})
