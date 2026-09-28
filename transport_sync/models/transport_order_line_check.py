# -*- coding: utf-8 -*-
"""ตรวจนับจำนวนสินค้าก่อนเริ่มงาน

คนขับต้องนับของจริงหน้าคลังก่อนถ่ายรูปและออกรถ ถ้าของขาดหรือเกินแล้วรู้ตอน
ถึงไซต์งานก็สายไปแล้ว เถียงกันไม่จบว่าขาดตั้งแต่คลังหรือหายระหว่างทาง

เก็บผลไว้ที่บรรทัดสินค้าโดยตรง ไม่แยกตาราง เพราะหนึ่งบรรทัดตรวจครั้งเดียว
ต่อหนึ่งเที่ยว และคนดูใบจองต้องเห็นพร้อมจำนวนที่สั่งในบรรทัดเดียวกัน
"""
from odoo import _, api, fields, models

CHECK_STATES = [
    ('pending', 'ยังไม่ตรวจ'),
    ('correct', 'ถูกต้อง'),
    ('incorrect', 'ไม่ถูกต้อง'),
]


class TransportOrderLineCheck(models.Model):
    _inherit = 'transport.order.line'

    check_state = fields.Selection(
        CHECK_STATES, string='ตรวจสอบจำนวนสินค้า', default='pending',
        index=True, copy=False,
        help='ผลการนับของจริงหน้าคลังโดยคนขับ ก่อนอนุญาตให้ถ่ายรูปและออกรถ')
    checked_quantity = fields.Float(
        string='จำนวนที่นับได้', copy=False,
        help='จำนวนจริงที่คนขับนับได้ กรอกเมื่อไม่ตรงกับที่สั่ง')
    quantity_diff = fields.Float(
        string='ผลต่าง', compute='_compute_quantity_diff', store=True,
        help='จำนวนที่นับได้ − จำนวนที่สั่ง ติดลบ = ของขาด')
    check_note = fields.Char(string='หมายเหตุการตรวจ', copy=False)
    checked_by_driver_id = fields.Many2one(
        'vehicle.driver', string='ผู้ตรวจนับ', readonly=True, copy=False)
    checked_at = fields.Datetime(
        string='เวลาที่ตรวจนับ', readonly=True, copy=False)

    @api.depends('check_state', 'checked_quantity', 'quantity')
    def _compute_quantity_diff(self):
        for line in self:
            if line.check_state == 'incorrect':
                line.quantity_diff = (line.checked_quantity or 0.0) - (line.quantity or 0.0)
            else:
                # ตรงหรือยังไม่ตรวจ ไม่มีผลต่างให้แสดง จะได้ไม่ชวนเข้าใจผิด
                line.quantity_diff = 0.0

    # ------------------------------------------------------------------
    def action_mark_correct(self):
        """ปุ่มบนหน้าจอ สำหรับคนหลังบ้านที่ตรวจแทนคนขับ"""
        return self._apply_check('correct')

    def action_mark_incorrect(self):
        return self._apply_check('incorrect')

    def _apply_check(self, state, checked_quantity=None, note=None, driver=None):
        values = {
            'check_state': state,
            'checked_at': fields.Datetime.now(),
        }
        if state == 'correct':
            # ถูกต้อง = นับได้เท่าที่สั่ง เก็บตัวเลขไว้ให้ตรวจสอบย้อนหลังได้
            values['checked_quantity'] = self[:1].quantity if len(self) == 1 else 0.0
        elif checked_quantity is not None:
            values['checked_quantity'] = checked_quantity
        if note is not None:
            values['check_note'] = note
        if driver:
            values['checked_by_driver_id'] = driver.id
        for line in self:
            line_values = dict(values)
            if state == 'correct':
                line_values['checked_quantity'] = line.quantity
            line.write(line_values)
        return True

    def action_reset_check(self):
        """ล้างผลตรวจ ให้คนขับตรวจใหม่"""
        return self.write({
            'check_state': 'pending',
            'checked_quantity': 0.0,
            'check_note': False,
            'checked_by_driver_id': False,
            'checked_at': False,
        })
