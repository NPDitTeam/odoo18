# -*- coding: utf-8 -*-
"""Pso. สาขาที่รับเอกสาร — บันทึกการรับเอกสารใบรับคืนสินค้าเข้าสาขา

ใช้เฉพาะเที่ยวที่ "รับสินค้าจากลูกค้ามายังสาขา" เพราะเป็นกรณีเดียวที่มีเอกสาร
ใบรับคืนสินค้าวิ่งกลับเข้าสาขาพร้อมของ ต้องมีหลักฐานว่าใครเป็นคนรับเอกสาร
รับเมื่อไหร่ และฝ่ายขายตรวจรับแล้วหรือยัง

เก็บเป็นชุดเดียวต่อใบจอง กดปุ่มซ้ำคือเปิดของเดิมขึ้นมาแก้ ไม่ได้สร้างใหม่
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

PSO_SALES_CHECK_STATES = [
    ('pending', 'รอฝ่ายขายตรวจ'),
    ('approved', 'รับใบรับคืนสินค้าตรวจรับเรียบร้อย'),
    ('rejected', 'ไม่ผ่าน — ตีกลับ'),
]


class VehicleBookingPsoDocument(models.Model):
    _inherit = 'vehicle.booking'

    pso_receiver_user_id = fields.Many2one(
        'res.users', string='ผู้รับเอกสาร', readonly=True, copy=False,
        tracking=True)
    pso_receive_branch_id = fields.Many2one(
        'res.branch', string='สาขาที่รับเอกสาร', readonly=True, copy=False)
    pso_receive_date = fields.Datetime(
        string='วันที่รับเอกสาร', readonly=True, copy=False)
    pso_sales_check_state = fields.Selection(
        PSO_SALES_CHECK_STATES, string='สถานะฝ่ายขายตรวจ',
        readonly=True, copy=False, tracking=True)
    pso_note = fields.Char(
        string='หมายเหตุฝ่ายขาย', readonly=True, copy=False,
        help='เหตุผลที่ตีกลับ หรือข้อสังเกตจากฝ่ายขาย')
    pso_attachment_ids = fields.Many2many(
        'ir.attachment', 'vehicle_booking_pso_attachment_rel',
        'booking_id', 'attachment_id', string='เอกสารแนบ', copy=False)
    pso_attachment_count = fields.Integer(
        string='จำนวนไฟล์แนบ', compute='_compute_pso_attachment_count')

    @api.depends('pso_attachment_ids')
    def _compute_pso_attachment_count(self):
        for record in self:
            record.pso_attachment_count = len(record.pso_attachment_ids)

    def action_open_pso_document_wizard(self):
        """เปิด popup บันทึกการรับเอกสาร (เปิดซ้ำ = แก้ของเดิม)"""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('บันทึกการรับเอกสารได้เมื่อการจองเสร็จสิ้นแล้วเท่านั้น'))
        if self.shipment_purpose != 'from_customer':
            raise UserError(_(
                'ใช้ได้เฉพาะเที่ยวที่ประเภทการจัดส่งสินค้าเป็น '
                '"รับสินค้าจากลูกค้ามายังสาขา"'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Pso.สาขาที่รับเอกสาร'),
            'res_model': 'vehicle.booking.pso.document.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_booking_id': self.id},
        }


class VehicleBookingPsoDocumentWizard(models.TransientModel):
    _name = 'vehicle.booking.pso.document.wizard'
    _description = 'Pso. สาขาที่รับเอกสาร'

    booking_id = fields.Many2one(
        'vehicle.booking', string='การจอง', required=True, ondelete='cascade')
    booking_name = fields.Char(
        related='booking_id.name', string='เลขที่จอง', readonly=True)
    receiver_user_id = fields.Many2one(
        'res.users', string='ผู้รับเอกสาร', required=True, readonly=True,
        default=lambda self: self.env.user)
    branch_id = fields.Many2one(
        'res.branch', string='สาขาที่รับเอกสาร', readonly=True)
    receive_date = fields.Datetime(
        string='วันที่รับเอกสาร', required=True,
        default=fields.Datetime.now)
    sales_check_state = fields.Selection(
        PSO_SALES_CHECK_STATES, string='สถานะฝ่ายขายตรวจ',
        required=True, default='pending')
    note = fields.Char(string='หมายเหตุฝ่ายขาย')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'pso_doc_wizard_attachment_rel',
        'wizard_id', 'attachment_id', string='เอกสารแนบ')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        booking_id = res.get('booking_id') or self.env.context.get('default_booking_id')
        if not booking_id:
            return res
        booking = self.env['vehicle.booking'].browse(booking_id)
        if not booking.exists():
            return res

        # สาขาที่รับเอกสารยึดตามใบจอง ไม่ให้เลือกเอง จะได้ไม่มีทางกรอกสวนกับ
        # สาขาที่วิ่งงานจริง
        res['branch_id'] = booking.branch_id.id

        # เปิดซ้ำต้องเห็นของเดิม ไม่ใช่ฟอร์มเปล่า ไม่งั้นกดบันทึกทีเดียว
        # ไฟล์แนบกับหมายเหตุที่เคยใส่ไว้จะถูกล้างทิ้งโดยไม่ตั้งใจ
        if booking.pso_receive_date:
            res.update({
                'receiver_user_id': booking.pso_receiver_user_id.id or self.env.uid,
                'receive_date': booking.pso_receive_date,
                'sales_check_state': booking.pso_sales_check_state or 'pending',
                'note': booking.pso_note or False,
                'attachment_ids': [(6, 0, booking.pso_attachment_ids.ids)],
            })
        return res

    def action_confirm(self):
        self.ensure_one()
        booking = self.booking_id
        attachments = self.attachment_ids

        if attachments:
            # ไฟล์ที่แนบในหน้าต่างนี้ผูกกับ record ชั่วคราว ซึ่ง Odoo เก็บกวาด
            # ทิ้งเป็นระยะ ต้องย้ายมาผูกกับใบจองก่อน ไม่งั้นไฟล์หายไปเองทีหลัง
            attachments.sudo().write({
                'res_model': 'vehicle.booking',
                'res_id': booking.id,
            })

        booking.write({
            'pso_receiver_user_id': self.receiver_user_id.id,
            'pso_receive_branch_id': self.branch_id.id,
            'pso_receive_date': self.receive_date,
            'pso_sales_check_state': self.sales_check_state,
            'pso_note': self.note or False,
            'pso_attachment_ids': [(6, 0, attachments.ids)],
        })
        return {'type': 'ir.actions.act_window_close'}
