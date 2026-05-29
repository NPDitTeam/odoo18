from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'
    lock_rent = fields.Boolean(string="ล็อกวันที่เช่า/วันที่ชำระ")
