# -*- coding: utf-8 -*-

from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True},  default=lambda self: self.env.user.branch_id.id)

class StockMOVE(models.Model):
    _inherit = "stock.move"

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True},  default=lambda self: self.env.user.branch_id.id)

class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True},  default=lambda self: self.env.user.branch_id.id)

class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    # operation type = config กลาง: ไม่ตั้ง default สาขา เพื่อไม่ให้ผูกสาขาโดยไม่ตั้งใจ
    # (record rule กรองสาขาของ stock.picking.type ถูกปิดใน security/branch_security.xml แล้ว)
    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True})


class AccountAccount(models.Model):
    _inherit = "account.account"

    # No default branch: the chart of accounts is shared across companies/branches
    # in Odoo 18, so accounts must be created with branch_id = False (global),
    # otherwise the "Account multi-branch" record rule rejects creation/import
    # whenever the creator's home branch is outside the active company selection.
    branch_id = fields.Many2one('res.branch', string='Branch',
                                help='Optional branch this account is restricted to. '
                                     'Leave empty to share the account across all branches.')
