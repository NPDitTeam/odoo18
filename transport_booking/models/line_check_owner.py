# -*- coding: utf-8 -*-
"""ผูกผลตรวจนับสินค้าเข้ากับ "เที่ยว" ไม่ใช่ "ใบขนส่ง"

ผลตรวจเก็บอยู่บน transport.order.line ซึ่งเป็นของใบขนส่ง (SO) แต่หนึ่งใบขนส่ง
วิ่งได้หลายเที่ยว — ไปส่งรอบแรกไม่หมดแล้ววิ่งซ้ำ ใบจองถูกยกเลิกแล้วจองใหม่
หรือใช้ "จองพร้อมกัน" แยกรถหลายคัน (ในฐานข้อมูลมีใบขนส่ง 55 ใบที่มีใบจอง
มากกว่าหนึ่ง)

เมื่อไม่ได้แยกว่าใครตรวจ เที่ยวที่สองจะเปิดมาเห็น "ตรวจครบแล้ว" ทั้งที่คนขับ
คนใหม่ยังไม่ได้แตะของเลย แล้วกดถ่ายรูปออกรถได้ทันที ซึ่งทำให้การตรวจนับ
ไม่มีความหมาย

จึงบันทึกไว้ว่าผลตรวจชุดนี้เป็นของใบจองใบไหน แล้วทุกที่ที่อ่านผลตรวจจะนับ
เฉพาะของใบจองที่กำลังดูอยู่
"""
from odoo import api, fields, models


class TransportOrderLineCheckOwner(models.Model):
    _inherit = 'transport.order.line'

    checked_booking_id = fields.Many2one(
        'vehicle.booking', string='ตรวจในเที่ยว', readonly=True, copy=False,
        ondelete='set null',
        help='ใบจองที่คนขับตรวจนับรอบนี้ ใช้แยกว่าผลตรวจเป็นของเที่ยวไหน')

    def _apply_check(self, state, checked_quantity=None, note=None,
                     driver=None, booking=None):
        res = super()._apply_check(state, checked_quantity=checked_quantity,
                                   note=note, driver=driver)
        if state == 'pending':
            self.write({'checked_booking_id': False})
        elif booking:
            self.write({'checked_booking_id': booking.id})
        return res

    def action_reset_check(self):
        res = super().action_reset_check()
        self.write({'checked_booking_id': False})
        return res

    def _check_state_for(self, booking):
        """สถานะตรวจของบรรทัดนี้ เมื่อมองจากใบจองที่ระบุ

        ผลตรวจของเที่ยวอื่นไม่นับ ถือว่ายังไม่ตรวจสำหรับเที่ยวนี้
        """
        self.ensure_one()
        if not booking or self.checked_booking_id != booking:
            return 'pending'
        return self.check_state or 'pending'


class VehicleBookingCheckOwner(models.Model):
    _inherit = 'vehicle.booking'

    @api.depends('transport_order_id',
                 'transport_order_id.order_line_ids',
                 'transport_order_id.order_line_ids.check_state',
                 'transport_order_id.order_line_ids.checked_booking_id',
                 'shipment_purpose', 'help_branch_note')
    def _compute_product_check(self):
        for booking in self:
            # เที่ยวช่วยสาขาไม่มีของให้ตรวจ ใช้หมายเหตุแทนเป็นเงื่อนไขปลดล็อกกล้อง
            if booking.shipment_purpose == 'help_branch':
                booking.product_check_total = 0
                booking.product_check_done = 0
                booking.product_check_mismatch = 0
                booking.product_check_state = 'no_line'
                booking.can_take_photo = bool(
                    (booking.help_branch_note or '').strip())
                continue
            lines = booking.transport_order_id.order_line_ids
            total = len(lines)
            # นับเฉพาะผลตรวจที่ทำในเที่ยวนี้ ของเที่ยวก่อนหน้าไม่นับ
            mine = lines.filtered(
                lambda l: l.checked_booking_id == booking
                and l.check_state != 'pending')
            mismatch = mine.filtered(lambda l: l.check_state == 'incorrect')
            booking.product_check_total = total
            booking.product_check_done = len(mine)
            booking.product_check_mismatch = len(mismatch)
            if not total:
                booking.product_check_state = 'no_line'
                booking.can_take_photo = True
            elif not mine:
                booking.product_check_state = 'pending'
                booking.can_take_photo = False
            elif len(mine) < total:
                booking.product_check_state = 'partial'
                booking.can_take_photo = False
            else:
                booking.product_check_state = 'done'
                booking.can_take_photo = True
