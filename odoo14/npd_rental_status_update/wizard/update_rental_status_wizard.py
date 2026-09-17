# -*- coding: utf-8 -*-
import logging

from markupsafe import Markup, escape

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Dictionary สำหรับแปลง rental_status เป็นภาษาไทย
RENTAL_STATUS_LABELS = {
    'due_date': 'ครบกำหนด',
    'nearly_due': 'ใกล้ครบกำหนด',
    'overdue': 'เกินกำหนด',
    'in_rent': 'อยู่ระหว่างการเช่า',
    'ready': 'ทำราคา',
    'done': 'ปิดบิล',
}


class UpdateRentalStatusWizard(models.TransientModel):
    _name = 'update.rental.status.wizard'
    _description = 'Wizard สำหรับอัพเดทสถานะ rental_status'

    order_ids = fields.Many2many('sale.order', string='รายการขาย')
    is_admin_user = fields.Boolean(string='มีสิทธิ์พิเศษ', default=False)
    new_status = fields.Selection([
        ('due_date', 'ครบกำหนด'),
        ('nearly_due', 'ใกล้ครบกำหนด'),
        ('overdue', 'เกินกำหนด'),
        ('in_rent', 'อยู่ระหว่างการเช่า'),
        ('ready', 'ทำราคา'),
        ('done', 'ปิดบิล'),
    ], string='สถานะใหม่', default='done')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['order_ids'] = [(6, 0, active_ids)]
        # ตรวจสอบสิทธิ์ผู้ใช้ (ใช้ sudo เพื่อให้อ่านค่าได้แน่นอน)
        res['is_admin_user'] = self.env['res.users'].sudo().browse(self.env.uid).allow_update_any_rental_status
        return res

    def _post_status_note(self, order, title, old_status, new_label):
        # o18 message_post escape ข้อความ str เป็นตัวหนังสือ ต้องห่อ Markup
        order.message_post(
            body=Markup('<strong>%s</strong><br/>ผู้ดำเนินการ: %s<br/>สถานะเดิม: %s<br/>สถานะใหม่: %s') % (
                title, escape(self.env.user.name), old_status, new_label),
            message_type='notification',
        )

    def action_update_status(self):
        """อัพเดทสถานะ rental_status ตามสิทธิ์ผู้ใช้"""
        if not self.order_ids:
            return {'type': 'ir.actions.act_window_close'}

        user = self.env.user
        is_admin = self.env['res.users'].sudo().browse(self.env.uid).allow_update_any_rental_status

        if is_admin:
            # ผู้ใช้มีสิทธิ์พิเศษ - อัพเดทเป็นสถานะที่เลือก
            new_status = self.new_status or 'done'
            new_status_label = RENTAL_STATUS_LABELS.get(new_status, new_status)
            for order in self.order_ids:
                old_status = RENTAL_STATUS_LABELS.get(order.rental_status, order.rental_status)
                _logger.info('Rental Status Update (Admin): User [%s] updated Order [%s] from [%s] to [%s]',
                             user.name, order.name, old_status, new_status_label)
                self._post_status_note(order, 'อัพเดทสถานะการเช่า (สิทธิ์พิเศษ)', old_status, new_status_label)
                order.write({'rental_status': new_status})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('สำเร็จ'),
                    'message': _('อัพเดทสถานะเป็น "%s" เรียบร้อยแล้ว จำนวน %s รายการ') % (
                        new_status_label, len(self.order_ids)),
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }

        # ผู้ใช้ทั่วไป - ปิดบิลได้เฉพาะ "ครบกำหนด" / "เกินกำหนด"
        allowed_statuses = ['due_date', 'overdue']
        valid_orders = self.order_ids.filtered(lambda o: o.rental_status in allowed_statuses)
        invalid_orders = self.order_ids - valid_orders
        if not valid_orders:
            raise UserError(_(
                'ไม่สามารถปิดบิลได้!\n\n'
                'ไม่มีรายการที่อยู่ในสถานะ "ครบกำหนด" หรือ "เกินกำหนด"\n\n'
                'กรุณาเลือกเฉพาะรายการที่มีสถานะ "ครบกำหนด" หรือ "เกินกำหนด" เท่านั้น'
            ))

        for order in valid_orders:
            old_status = RENTAL_STATUS_LABELS.get(order.rental_status, order.rental_status)
            _logger.info('Rental Status Update: User [%s] updated Order [%s] from [%s] to [done/ปิดบิล]',
                         user.name, order.name, old_status)
            self._post_status_note(order, 'อัพเดทสถานะการเช่า', old_status, 'ปิดบิล')
            order.write({'rental_status': 'done'})

        message = _('อัพเดทสถานะเป็น "ปิดบิล" เรียบร้อยแล้ว จำนวน %s รายการ') % len(valid_orders)
        if invalid_orders:
            message += _('\n\nรายการที่ไม่ได้อัพเดท (สถานะไม่ถูกต้อง): %s') % ', '.join(invalid_orders.mapped('name'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('สำเร็จ'),
                'message': message,
                'type': 'success' if not invalid_orders else 'warning',
                'sticky': bool(invalid_orders),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
