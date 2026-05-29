from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    fleet_refund = fields.Boolean(string="คืนเงินโอนเกิน/คืนหัก ณ ที่จ่าย")
