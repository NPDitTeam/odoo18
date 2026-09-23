# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    scrap_branch_id = fields.Many2one(
        'res.branch',
        string='สาขาของคลังพักสินค้า',
        index=True,
        help='ใช้กับคลังพักสินค้าที่แตกลูกรายสาขา เช่น "ขายตามสภาพ/ลาดกระบัง"\n'
             '\n'
             'ทำไมไม่ใช้ฟิลด์ "สาขา" (branch_id) ปกติ:\n'
             'โมดูลอื่นหาคลังต้นทางของสาขาด้วย\n'
             "    search([('branch_id','=',x), ('usage','=','internal')], limit=1)\n"
             'โดยไม่ระบุลำดับ จึงใช้ _order = "complete_name, id" ของ stock.location\n'
             'ถ้าคลังพักผูก branch_id ด้วย ชื่อที่ขึ้นต้นด้วย "ข" จะมาก่อน "บ"\n'
             'ทำให้ระบบไปตัดสต๊อกจากคลังพักที่ว่างเปล่า -> สต๊อกติดลบ\n'
             'จึงแยกมาเก็บที่ฟิลด์นี้แทน ไม่ชนกับการค้นหาเดิม',
    )
