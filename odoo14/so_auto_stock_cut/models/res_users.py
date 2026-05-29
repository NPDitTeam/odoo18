from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    allow_greenhome_return = fields.Boolean(
        string='อนุญาตให้คืนสินค้าบ้านเขียว',
        default=False,
        help='หากติ๊กถูก จะแสดงปุ่ม "คืนสินค้าบ้านเขียว" ในวิซาร์ดตัดสต๊อก'
    )
