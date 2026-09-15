# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ไม่เพิ่มเข้า SELF_WRITEABLE_FIELDS: ผู้ใช้ห้ามเปิดสิทธิ์ให้ตัวเอง
    allow_edit_head_office_branch = fields.Boolean(
        string='แก้ไขสาขาสำนักงานใหญ่เองได้',
        default=False,
        help='ติ๊กถูก: แก้ฟิลด์ "สาขาสำนักงานใหญ่" เองได้ ในเมนู บิลผู้ขาย / Avance Clear / การรับ\n'
             'ไม่ติ๊ก: ฟิลด์เป็นแบบอ่านอย่างเดียว ระบบเติมให้อัตโนมัติจากการกำหนดค่าสาขา',
    )
