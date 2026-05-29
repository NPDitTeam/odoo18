from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'
    bypass_rental_tax_lock = fields.Boolean(string="ข้ามการล็อกภาษี", default=False)
