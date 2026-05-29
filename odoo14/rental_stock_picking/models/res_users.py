from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    can_edit_force_date = fields.Boolean(
        string='อนุญาตให้แก้ไขวันที่บังคับ (Force Date)',
        default=False,
    )
