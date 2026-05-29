from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    refund_of_rental = fields.Boolean(string="คืนเงินประกันค่าเช่า")
    can_edit_voucher_lines = fields.Boolean(string="แก้ไขรายการ Voucher Lines ได้")
