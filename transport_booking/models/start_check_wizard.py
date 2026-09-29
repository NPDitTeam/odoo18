# -*- coding: utf-8 -*-
"""ตรวจนับสินค้าก่อนเริ่มขนส่ง สำหรับคนที่สั่งงานจากหน้าจอ Odoo

แอปคนขับบังคับตรวจนับทุกรายการก่อนถ่ายรูปและออกรถอยู่แล้ว แต่เที่ยวที่สั่ง
จากหน้าจอ Odoo เดิมกดเริ่มขนส่งได้เลย ทำให้สองทางได้หลักฐานไม่เท่ากัน
เที่ยวที่ของขาดแล้วสั่งจาก Odoo จึงไม่มีอะไรยืนยันว่าขาดตั้งแต่คลัง

ตัวช่วยนี้เขียนผลลงฟิลด์ชุดเดียวกับที่แอปใช้ (check_state บน
transport.order.line) รายงานและหน้าจอที่มีอยู่จึงอ่านได้ทันทีโดยไม่ต้องแก้

ใช้ตารางชั่วคราวคัดลอกค่ามาก่อน ไม่ได้แก้บรรทัดจริงตรง ๆ เพื่อให้กดยกเลิก
กลางคันแล้วไม่มีอะไรเปลี่ยน
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# ใช้ตัวเลือกชุดเดียวกับที่แอปเขียนลงบรรทัดจริง ไม่ประกาศซ้ำ ไม่งั้นแก้ที่เดียว
# แล้วอีกที่ไม่ตาม กลายเป็นค่าที่บันทึกไม่ตรงกัน
from odoo.addons.transport_sync.models.transport_order_line_check import (
    CHECK_STATES,
)


class VehicleBookingStartCheck(models.Model):
    _inherit = 'vehicle.booking'

    start_check_photo_ids = fields.Many2many(
        'ir.attachment',
        'vehicle_booking_start_photo_rel', 'booking_id', 'attachment_id',
        string='รูปสินค้าก่อนขนส่ง', copy=False)
    start_check_photo_count = fields.Integer(
        string='จำนวนรูปก่อนขนส่ง', compute='_compute_start_check_photo_count')

    @api.depends('start_check_photo_ids')
    def _compute_start_check_photo_count(self):
        for record in self:
            record.start_check_photo_count = len(record.start_check_photo_ids)

    def action_open_start_check_wizard(self):
        """เปิด popup ตรวจนับสินค้า แล้วค่อยเริ่มขนส่ง

        ปุ่มบนหน้าจอเรียกตัวนี้แทน action_start โดยตรง ส่วน action_start
        ยังคงเดิมเพราะแอปคนขับเรียกผ่าน start_job_with_photo อยู่
        """
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('เริ่มขนส่งได้เฉพาะรายการที่ยืนยันการจองแล้ว'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('ตรวจนับสินค้าก่อนเริ่มขนส่ง'),
            'res_model': 'vehicle.booking.start.check.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_booking_id': self.id},
        }


class VehicleBookingStartCheckWizard(models.TransientModel):
    _name = 'vehicle.booking.start.check.wizard'
    _description = 'ตรวจนับสินค้าก่อนเริ่มขนส่ง'

    booking_id = fields.Many2one(
        'vehicle.booking', string='การจอง', required=True, ondelete='cascade')
    booking_name = fields.Char(
        related='booking_id.name', string='เลขที่จอง', readonly=True)
    driver_name = fields.Char(
        related='booking_id.driver_id.name', string='คนขับ', readonly=True)
    vehicle_name = fields.Char(
        related='booking_id.vehicle_id.display_name', string='รถที่จัดส่ง',
        readonly=True)

    line_ids = fields.One2many(
        'vehicle.booking.start.check.line', 'wizard_id',
        string='รายการสินค้า')
    photo_ids = fields.Many2many(
        'ir.attachment', 'start_check_wizard_photo_rel',
        'wizard_id', 'attachment_id', string='รูปสินค้า')

    needs_product_check = fields.Boolean(
        related='booking_id.needs_product_check', readonly=True,
        string='ต้องตรวจนับสินค้า')
    help_branch_note = fields.Text(
        string='หมายเหตุการไปช่วยสาขา',
        help='ระบุว่าไปช่วยสาขาไหน ทำอะไรมา — ระบบจะให้ AI ตรวจว่าตรงกับ'
             'ประเภทการจัดส่งที่เลือกไว้หรือไม่')

    # ผล AI อ่านจากใบจองโดยตรง กดตรวจแล้วเปิด popup ใหม่จะเห็นค่าล่าสุดทันที
    note_ai_state = fields.Selection(
        related='booking_id.help_branch_ai_state', readonly=True,
        string='ผล AI ตรวจหมายเหตุ')
    note_ai_message = fields.Text(
        related='booking_id.help_branch_ai_message', readonly=True,
        string='ความเห็น AI')
    note_ai_example = fields.Text(
        related='booking_id.help_branch_ai_example', readonly=True,
        string='ตัวอย่างที่ AI แนะนำ')

    total_count = fields.Integer(compute='_compute_progress')
    checked_count = fields.Integer(compute='_compute_progress')
    mismatch_count = fields.Integer(compute='_compute_progress')
    all_checked = fields.Boolean(compute='_compute_progress')
    progress_text = fields.Char(compute='_compute_progress')

    @api.depends('line_ids.check_state')
    def _compute_progress(self):
        for wiz in self:
            lines = wiz.line_ids
            checked = lines.filtered(lambda l: l.check_state != 'pending')
            mismatch = lines.filtered(lambda l: l.check_state == 'incorrect')
            wiz.total_count = len(lines)
            wiz.checked_count = len(checked)
            wiz.mismatch_count = len(mismatch)
            # ไม่มีรายการสินค้าก็ไม่ควรขวางไม่ให้ออกรถ
            wiz.all_checked = not lines or len(checked) == len(lines)
            if not lines:
                wiz.progress_text = 'ใบจองนี้ไม่มีรายการสินค้าให้ตรวจ'
            elif len(checked) == len(lines):
                wiz.progress_text = 'ตรวจครบแล้ว %d รายการ' % len(lines)
            else:
                wiz.progress_text = 'ตรวจแล้ว %d จาก %d รายการ' % (
                    len(checked), len(lines))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        booking_id = res.get('booking_id') or self.env.context.get('default_booking_id')
        if not booking_id:
            return res
        booking = self.env['vehicle.booking'].browse(booking_id)
        if not booking.exists():
            return res

        # ดึงผลตรวจเดิมมาด้วย เผื่อคนขับตรวจผ่านแอปไปแล้วบางส่วน
        # จะได้ไม่ต้องตรวจซ้ำและเห็นว่าใครตรวจอะไรไว้
        lines = []
        for line in booking.transport_order_id.order_line_ids:
            lines.append((0, 0, {
                'order_line_id': line.id,
                'product_name': line.product_name_o14 or '',
                'quantity': line.quantity or 0.0,
                'uom_name': line.uom_name or '',
                # ผลตรวจของเที่ยวก่อนหน้าไม่นับ เที่ยวนี้ต้องตรวจใหม่
                'check_state': line._check_state_for(booking),
                'checked_quantity': (line.checked_quantity or 0.0
                                     if line.checked_booking_id == booking else 0.0),
                'check_note': (line.check_note or False
                               if line.checked_booking_id == booking else False),
            }))
        res['line_ids'] = lines
        if booking.shipment_purpose == 'help_branch':
            res['help_branch_note'] = booking.help_branch_note or False
        if booking.start_check_photo_ids:
            res['photo_ids'] = [(6, 0, booking.start_check_photo_ids.ids)]
        return res

    # ------------------------------------------------------------------
    def action_mark_all_correct(self):
        """ปุ่มลัดตอนของครบทุกอย่าง ซึ่งเป็นกรณีส่วนใหญ่"""
        self.ensure_one()
        self.line_ids.write({'check_state': 'correct'})
        # ต้องคืน action เดิมเพื่อให้ popup เปิดค้างไว้ ไม่ใช่ปิดไปเลย
        return {
            'type': 'ir.actions.act_window',
            'name': _('ตรวจนับสินค้าก่อนเริ่มขนส่ง'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_check_note(self):
        """ตรวจหมายเหตุด้วย AI โดยยังไม่เริ่มขนส่ง

        คนกรอกจะได้เห็นความเห็นกับตัวอย่างก่อน แล้วแก้ข้อความได้เหมือนในแอป
        ถ้าให้เห็นผลตอนกดยืนยันอย่างเดียว งานก็เริ่มไปแล้ว แก้ไม่ทัน
        """
        self.ensure_one()
        self.booking_id._save_help_branch_note(self.help_branch_note)
        # เปิดหน้าต่างเดิมซ้ำเพื่อให้ค่าที่ AI เพิ่งเขียนขึ้นมาแสดง
        return {
            'type': 'ir.actions.act_window',
            'name': _('ตรวจนับสินค้าก่อนเริ่มขนส่ง'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_use_ai_example(self):
        """เติมตัวอย่างที่ AI ร่างไว้ลงช่องหมายเหตุ ให้แก้ต่อได้เลย"""
        self.ensure_one()
        if self.note_ai_example:
            self.help_branch_note = self.note_ai_example
        return {
            'type': 'ir.actions.act_window',
            'name': _('ตรวจนับสินค้าก่อนเริ่มขนส่ง'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()
        booking = self.booking_id

        # เที่ยวช่วยสาขาไม่มีของให้ตรวจ ใช้หมายเหตุแทนแล้วให้ AI อ่านเทียบ
        if booking.shipment_purpose == 'help_branch':
            booking._save_help_branch_note(self.help_branch_note)

        # รูปคือหลักฐานว่าของสภาพไหนตอนออกจากคลัง ถ้าไม่บังคับก็จะไม่มีใครถ่าย
        # แล้วเวลาของเสียหายปลายทางก็เถียงกันไม่จบเหมือนเดิม
        if not self.photo_ids:
            raise UserError(_('กรุณาแนบรูปสินค้าอย่างน้อย 1 รูป ก่อนเริ่มขนส่ง'))

        if not self.all_checked:
            raise UserError(_(
                'ยังตรวจไม่ครบทุกรายการ (%(done)s จาก %(total)s) '
                'กรุณาระบุว่าแต่ละรายการถูกต้องหรือไม่ก่อนเริ่มขนส่ง',
                done=self.checked_count, total=self.total_count))

        driver = booking.driver_id
        for line in self.line_ids:
            real = line.order_line_id
            if not real:
                continue
            real._apply_check(
                line.check_state,
                checked_quantity=(line.checked_quantity
                                  if line.check_state == 'incorrect' else None),
                note=line.check_note or '',
                driver=driver,
                booking=booking,
            )

        if self.photo_ids:
            # รูปที่แนบใน popup ผูกกับ record ชั่วคราวซึ่งถูกเก็บกวาดทิ้ง
            # เป็นระยะ ต้องย้ายมาผูกกับใบจองก่อน ไม่งั้นรูปหายไปเองทีหลัง
            self.photo_ids.sudo().write({
                'res_model': 'vehicle.booking',
                'res_id': booking.id,
            })
            values = {'start_check_photo_ids': [(6, 0, self.photo_ids.ids)]}
            # หน้าจอเดิม ประวัติการจัดส่ง และรายงาน อ่านจาก pickup_photo
            # ซึ่งเก็บได้รูปเดียว ใส่รูปแรกไว้ให้ของเดิมยังทำงานเหมือนเคย
            if not booking.pickup_photo:
                first = self.photo_ids[0]
                if first.datas:
                    values['pickup_photo'] = first.datas
            booking.write(values)

        booking.action_start()
        return {'type': 'ir.actions.act_window_close'}


class VehicleBookingStartCheckLine(models.TransientModel):
    _name = 'vehicle.booking.start.check.line'
    _description = 'รายการสินค้าที่ต้องตรวจก่อนเริ่มขนส่ง'

    wizard_id = fields.Many2one(
        'vehicle.booking.start.check.wizard', required=True, ondelete='cascade')
    order_line_id = fields.Many2one(
        'transport.order.line', string='บรรทัดสินค้า', required=True,
        ondelete='cascade')

    product_name = fields.Char(string='ชื่อสินค้า', readonly=True)
    quantity = fields.Float(string='จำนวนที่สั่ง', readonly=True)
    uom_name = fields.Char(string='หน่วย', readonly=True)

    check_state = fields.Selection(
        CHECK_STATES, string='ตรวจสอบจำนวนสินค้า', default='pending',
        required=True)
    checked_quantity = fields.Float(string='จำนวนที่นับได้')
    check_note = fields.Char(string='หมายเหตุ')
    quantity_diff = fields.Float(
        string='ผลต่าง', compute='_compute_quantity_diff')

    @api.depends('check_state', 'checked_quantity', 'quantity')
    def _compute_quantity_diff(self):
        for line in self:
            if line.check_state == 'incorrect':
                line.quantity_diff = (line.checked_quantity or 0.0) - (line.quantity or 0.0)
            else:
                line.quantity_diff = 0.0

    @api.onchange('check_state')
    def _onchange_check_state(self):
        """เลือกว่าถูกต้อง = นับได้เท่าที่สั่ง กรอกซ้ำอีกช่องก็ไม่มีประโยชน์"""
        for line in self:
            if line.check_state == 'correct':
                line.checked_quantity = line.quantity
                line.check_note = False
            elif line.check_state == 'pending':
                line.checked_quantity = 0.0
