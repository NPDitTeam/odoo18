# -*- coding: utf-8 -*-
from odoo import models, fields


class VehicleBookingDoneReasonWizard(models.TransientModel):
    _name = 'vehicle.booking.done.reason.wizard'
    _description = 'ระบุเหตุผลที่ไม่ใช้งานผ่านแอป (เสร็จสิ้น)'

    booking_id = fields.Many2one(
        'vehicle.booking',
        string='การจอง',
        required=True,
        ondelete='cascade',
    )
    reason = fields.Text(
        string='เหตุผลที่ไม่ใช้งานผ่านแอป',
        required=True,
    )

    def action_confirm(self):
        """บันทึกเหตุผลลงในการจอง แล้วดำเนินการเสร็จสิ้น"""
        self.ensure_one()
        self.booking_id.write({'no_app_done_reason': self.reason})
        self.booking_id.action_done()
        return {'type': 'ir.actions.act_window_close'}
