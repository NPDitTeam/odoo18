from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'
    allow_payment_reprocess = fields.Boolean(string="ดำเนินการรับชำระใหม่", default=False)
