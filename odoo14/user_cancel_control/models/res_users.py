from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    allow_cancel = fields.Boolean(
        string='อนุญาตให้ยกเลิก',
        default=False,
        help='ถ้าเลือกไว้ ผู้ใช้จะสามารถยกเลิกใบรับชำระ/บันทึก/ใบสั่งขาย ถ้าไม่เลือก จะไม่สามารถยกเลิกได้'
    )
