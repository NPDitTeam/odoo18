from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    account_payment_lock_draft_date = fields.Boolean(
        string='สามารถรีเซ็ต Payment เป็นร่างได้',
        default=False,
    )
