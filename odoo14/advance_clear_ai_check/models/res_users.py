from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    allow_reset_draft_keep_ai = fields.Boolean(
        string='อนุญาตให้ Reset to Draft (Keep AI)',
        default=False,
        help='ถ้าติ๊กถูก ผู้ใช้นี้สามารถกด Reset to Draft โดยเก็บผลการตรวจสอบ AI ไว้ได้ '
             'ถ้าไม่ติ๊ก จะไม่เห็นปุ่มนี้'
    )
