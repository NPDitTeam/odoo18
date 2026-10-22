# -*- coding: utf-8 -*-
"""เลือกคำสั่งขนส่งในหน้าจองคิวรถ → ตรวจว่าสินค้ามีจำนวนไหม (ผู้ใช้สั่ง 22 ต.ค. 2569)

จำนวนเป็น 0 → ดึงจาก Odoo 14 ใหม่ · o14 ก็ยังไม่มีจำนวน → เตือนให้ไประบุที่ o14
"""
from odoo import api, models


class VehicleBookingQtyRefresh(models.Model):
    _inherit = 'vehicle.booking'

    @api.onchange('transport_order_id')
    def _onchange_transport_order_check_qty(self):
        order = self.transport_order_id
        if not order:
            return None
        fixed, still_zero, reached = order.sudo().npd_refresh_zero_qty_from_o14()
        if still_zero:
            names = '\n'.join('- %s' % (line.product_name_o14 or line.product_id.display_name or '?')
                              for line in still_zero[:15])
            more = '\n... และอีก %d รายการ' % (len(still_zero) - 15) if len(still_zero) > 15 else ''
            head = ('จำนวนสินค้า o14 ยังไม่ได้ระบุ กรุณาระบุ' if reached
                    else 'ดึงจำนวนสินค้าจาก o14 ไม่สำเร็จ (ติดต่อ o14 ไม่ได้) กรุณาตรวจจำนวนสินค้าใน o14')
            return {
                'warning': {
                    'title': 'จำนวนสินค้า o14 ยังไม่ได้ระบุ',
                    'message': '%s\n\nคำสั่งขนส่ง %s มีสินค้าที่จำนวนเป็น 0:\n%s%s' % (head, order.name, names, more),
                }
            }
        if fixed:
            return {
                'warning': {
                    'title': 'ดึงจำนวนสินค้าจาก o14 แล้ว',
                    'message': 'คำสั่งขนส่ง %s ดึงจำนวนสินค้าจาก o14 ใหม่ %d รายการ' % (order.name, fixed),
                    'type': 'notification',
                }
            }
        return None
