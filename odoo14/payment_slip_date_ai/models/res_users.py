from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    allow_skip_slip_date_check = fields.Boolean(
        string='อนุญาตข้ามการตรวจวันที่จากสลิป',
        default=False,
        help='ถ้าติ๊กถูก ผู้ใช้นี้สามารถกด "ยืนยัน" (post) ใบรับชำระได้ '
             'โดยไม่ต้องผ่านเงื่อนไขกดปุ่ม "ใช้วันที่จากสลิป" '
             'ใช้เป็นทางออกในกรณี AI อ่านสลิปไม่ได้',
    )
