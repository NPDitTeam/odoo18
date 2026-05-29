from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'
    is_advance_clear_approver = fields.Boolean(string="เป็นผู้ตรวจสอบ Advance Clear", default=False)
