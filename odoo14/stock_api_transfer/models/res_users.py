# -*- coding: utf-8 -*-
from odoo import models, fields


class ResUsers(models.Model):
    _inherit = "res.users"

    is_stock_transfer_approver = fields.Boolean(
        string="ผู้อนุมัติการโยกสินค้า",
        compute="_compute_is_stock_transfer_approver",
        inverse="_inverse_is_stock_transfer_approver",
        groups="base.group_erp_manager",
    )

    def _compute_is_stock_transfer_approver(self):
        approver_group = self.env.ref(
            'stock_api_transfer.group_stock_transfer_approver', raise_if_not_found=False)
        for user in self:
            user.is_stock_transfer_approver = approver_group in user.groups_id if approver_group else False

    def _inverse_is_stock_transfer_approver(self):
        approver_group = self.env.ref(
            'stock_api_transfer.group_stock_transfer_approver', raise_if_not_found=False)
        if not approver_group:
            return
        for user in self:
            if user.is_stock_transfer_approver:
                user.groups_id = [(4, approver_group.id)]
            else:
                user.groups_id = [(3, approver_group.id)]
