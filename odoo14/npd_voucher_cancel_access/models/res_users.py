from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'
    allow_cancel_voucher = fields.Boolean(string="อนุญาตยกเลิกใบคืนเงินประกันค่าเช่า", default=False)
