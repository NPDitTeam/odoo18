from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'
    allow_update_any_rental_status = fields.Boolean(string="อนุญาตปรับสถานะการเช่าได้ทุกสถานะ", default=False)
