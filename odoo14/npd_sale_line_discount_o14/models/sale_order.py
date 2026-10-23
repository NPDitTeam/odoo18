# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _show_cancel_wizard(self):
        # กดยกเลิกแล้วยกเลิกเลย ไม่เปิดหน้าส่งอีเมลแจ้งลูกค้า (ผู้ใช้สั่ง 23 ต.ค. 2569)
        return False
