from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    bypass_branch_filter = fields.Boolean(
        string='แสดงทุกสาขาในใบแจ้งหนี้',
        help='When checked, this user can see all account moves regardless of branch restrictions'
    )
    bypass_branch_filter_payment = fields.Boolean(
        string='แสดงทุกสาขาในใบรับชำระ',
        help='When checked, this user can see all account payment regardless of branch restrictions'
    )
