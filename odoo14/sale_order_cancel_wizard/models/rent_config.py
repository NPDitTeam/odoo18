from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    cancel_rent_same_day = fields.Boolean(string="ยกเลิกภายในวันได้")
