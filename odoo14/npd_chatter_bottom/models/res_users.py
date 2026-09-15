from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ฟิลด์มาจาก muk_web_chatter (side/bottom ค่าเริ่มต้น side) — เปลี่ยนค่าเริ่มต้นเป็นด้านล่างแบบ o14
    chatter_position = fields.Selection(
        selection=[
            ('bottom', 'ด้านล่าง'),
            ('side', 'ด้านข้าง'),
        ],
        string='ตำแหน่งช่องบันทึก (Chatter)',
        default='bottom',
        help='ด้านล่าง = ช่องส่งข้อความ/บันทึกโน้ต/ประวัติ อยู่ใต้เอกสาร\n'
             'ด้านข้าง = อยู่ด้านขวาของเอกสาร (ลากขยายความกว้างได้)',
    )
