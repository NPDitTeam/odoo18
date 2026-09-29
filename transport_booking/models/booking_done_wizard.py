# -*- coding: utf-8 -*-
"""ปิดงานขนส่งจากหน้าจอ Odoo

เที่ยวที่ปิดจากแอปจะได้ชื่อผู้รับ ตำแหน่งผู้รับ รูป และลายเซ็นครบ ส่วนเที่ยว
ที่ปิดจากหน้าจอ Odoo เดิมกรอกแค่เหตุผลที่ไม่ใช้แอป ทำให้ของสองทางเทียบกัน
ไม่ได้เวลามีปัญหาย้อนหลังว่าใครเป็นคนเซ็นรับ

จึงบังคับกรอกชื่อและตำแหน่งผู้รับเหมือนกับที่แอปบังคับ และเขียนลงฟิลด์
ชุดเดียวกัน (receiver_name / receiver_position) รายงานจึงอ่านได้ที่เดียว
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class VehicleBookingDoneReasonWizard(models.TransientModel):
    _name = 'vehicle.booking.done.reason.wizard'
    _description = 'ระบุเหตุผลที่ไม่ใช้งานผ่านแอป (เสร็จสิ้น)'

    booking_id = fields.Many2one(
        'vehicle.booking',
        string='การจอง',
        required=True,
        ondelete='cascade',
    )
    booking_name = fields.Char(
        related='booking_id.name', string='เลขที่จอง', readonly=True)
    # เที่ยวช่วยสาขาไม่มีผู้รับสินค้า มีแต่คนของสาขาปลายทางที่รับรองว่าไปช่วยจริง
    needs_product_check = fields.Boolean(
        related='booking_id.needs_product_check', readonly=True)
    shipment_purpose = fields.Selection(
        related='booking_id.shipment_purpose', readonly=True,
        string='ประเภทการจัดส่งสินค้า')

    # บังคับแนบเหมือนที่แอปบังคับ เพื่อให้เที่ยวที่ปิดจาก Odoo มีหลักฐาน
    # เท่ากับเที่ยวที่ปิดจากแอป ไม่งั้นคนที่อยากเลี่ยงการถ่ายรูปก็แค่มาปิดที่นี่
    photo_ids = fields.Many2many(
        'ir.attachment', 'booking_done_wizard_photo_rel',
        'wizard_id', 'attachment_id', string='รูปตอนจบงาน')

    # ดึงจากใบจองให้เลย คนกรอกเป็นแอดมินหลังบ้าน ไม่ใช่คนขับ จะพิมพ์ชื่อเอง
    # แล้วสะกดไม่ตรงกับทะเบียนคนขับ
    driver_id = fields.Many2one(
        related='booking_id.driver_id', string='คนขับรถ', readonly=True)
    vehicle_id = fields.Many2one(
        related='booking_id.vehicle_id', string='รถที่จัดส่ง', readonly=True)

    receiver_name = fields.Char(
        string='ชื่อผู้รับ / ผู้รับรอง', required=True)
    receiver_position = fields.Char(
        string='ตำแหน่งผู้รับ / ผู้รับรอง', required=True,
        help='เที่ยวส่งของ: ตำแหน่งของคนที่รับของ เช่น เจ้าของบ้าน ยาม หัวหน้าช่าง\n'
             'เที่ยวช่วยสาขา: ตำแหน่งของคนที่สาขาปลายทางซึ่งรับรองว่าไปช่วยจริง '
             'เช่น หัวหน้าสาขา พนักงานคลัง')
    signed_by_self = fields.Boolean(
        string='เซ็นแทน (ไม่เจอผู้รับ/ผู้รับรอง)')

    reason = fields.Text(
        string='เหตุผลที่ไม่ใช้งานผ่านแอป',
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        booking_id = res.get('booking_id') or self.env.context.get('default_booking_id')
        if not booking_id:
            return res
        booking = self.env['vehicle.booking'].browse(booking_id)
        if not booking.exists():
            return res
        # เผื่อคนขับกรอกผ่านแอปไปแล้วบางส่วนก่อนจะมาปิดงานจากหลังบ้าน
        if booking.receiver_name:
            res.setdefault('receiver_name', booking.receiver_name)
        if booking.receiver_position:
            res.setdefault('receiver_position', booking.receiver_position)
        res.setdefault('signed_by_self', booking.signed_by_self)
        return res

    def action_confirm(self):
        """บันทึกข้อมูลผู้รับและเหตุผล แล้วดำเนินการเสร็จสิ้น"""
        self.ensure_one()

        # required=True ของฟิลด์ใหม่ไม่ได้กลายเป็น NOT NULL ในฐาน เพราะตาราง
        # มีแถวเก่าอยู่ตอนอัปเดตโมดูล หน้าจอกันให้ชั้นหนึ่งแล้ว แต่ถ้ามีใคร
        # เรียกเมธอดนี้ตรง ๆ จะหลุดไปได้ จึงต้องกันซ้ำตรงนี้
        name = (self.receiver_name or '').strip()
        position = (self.receiver_position or '').strip()
        if not self.photo_ids:
            raise UserError(_('กรุณาแนบรูปอย่างน้อย 1 รูปก่อนปิดงาน'))

        if not name or not position:
            label = 'ผู้รับ' if self.needs_product_check else 'ผู้รับรอง'
            raise UserError(_(
                'กรุณากรอกทั้งชื่อ%(label)sและตำแหน่ง%(label)sก่อนปิดงาน',
                label=label))

        if self.photo_ids:
            # รูปที่แนบในหน้าต่างนี้ผูกกับ record ชั่วคราวซึ่งถูกเก็บกวาดทิ้ง
            # เป็นระยะ ต้องย้ายมาผูกกับใบจองก่อน ไม่งั้นรูปหายไปเองทีหลัง
            self.photo_ids.sudo().write({
                'res_model': 'vehicle.booking',
                'res_id': self.booking_id.id,
            })
            self.booking_id.write({
                'delivery_photo_ids': [(4, a.id) for a in self.photo_ids],
            })
            # หน้าจอเดิม ประวัติการจัดส่ง และรายงาน อ่านจาก delivery_photo
            # ซึ่งเก็บได้รูปเดียว ใส่รูปแรกไว้ให้ของเดิมยังทำงานเหมือนเคย
            if not self.booking_id.delivery_photo and self.photo_ids[0].datas:
                self.booking_id.write(
                    {'delivery_photo': self.photo_ids[0].datas})

        self.booking_id.write({
            'no_app_done_reason': self.reason,
            'receiver_name': name,
            'receiver_position': position,
            'signed_by_self': self.signed_by_self,
        })
        self.booking_id.action_done()
        return {'type': 'ir.actions.act_window_close'}
