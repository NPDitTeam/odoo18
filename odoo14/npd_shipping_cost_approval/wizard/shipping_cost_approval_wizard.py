# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ShippingCostApprovalWizard(models.TransientModel):
    _name = 'shipping.cost.approval.wizard'
    _description = 'อนุมัติค่าขนส่งพิเศษ'

    sale_order_id = fields.Many2one('sale.order', string='ใบสั่งขาย', required=True, readonly=True)
    mode = fields.Selection(
        [('request', 'ขออนุมัติ'), ('approve', 'อนุมัติ'), ('reject', 'ไม่อนุมัติ')],
        required=True, default='request', readonly=True)
    approver_id = fields.Many2one(
        'res.users', string='ผู้อนุมัติ', domain=lambda self: self._approver_domain())
    reason = fields.Text(string='เหตุผลในการขออนุมัติ')
    note = fields.Text(string='ความเห็นผู้อนุมัติ')

    use_special_delivery_zero = fields.Boolean(
        related='sale_order_id.use_special_delivery_zero', string='ใช้ค่าขนส่งพิเศษที่เป็น 0')
    shipping_cost = fields.Float(related='sale_order_id.shipping_cost', string='ค่าขนส่ง (คำนวณ)')
    shipping_cost_m = fields.Float(related='sale_order_id.shipping_cost_m', string='ค่าขนส่งพิเศษ')
    request_user_id = fields.Many2one(related='sale_order_id.ship_request_user_id')

    @api.model
    def _approver_domain(self):
        group = self.env.ref('npd_shipping_cost_approval.group_ship_cost_approver')
        return [('groups_id', 'in', group.id), ('share', '=', False)]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env['sale.order'].browse(res.get('sale_order_id'))
        if order and res.get('mode') in ('approve', 'reject'):
            res.setdefault('approver_id', order.ship_approver_id.id)
            res.setdefault('reason', order.ship_approval_reason)
        return res

    def action_confirm(self):
        self.ensure_one()
        order = self.sale_order_id
        if self.mode == 'request':
            if not self.approver_id:
                raise UserError(_('กรุณาเลือกผู้อนุมัติ'))
            if not self.approver_id.has_group('npd_shipping_cost_approval.group_ship_cost_approver'):
                raise UserError(_('%s ไม่มีสิทธิ์ "ผู้อนุมัติค่าขนส่งพิเศษ"') % self.approver_id.name)
            if not (self.reason or '').strip():
                raise UserError(_('กรุณาใส่เหตุผลในการขออนุมัติ'))
            order._ship_do_request(self.approver_id, self.reason.strip())
        elif self.mode == 'approve':
            order._ship_do_decide(True, (self.note or '').strip())
        else:
            if not (self.note or '').strip():
                raise UserError(_('กรุณาใส่เหตุผลที่ไม่อนุมัติ'))
            order._ship_do_decide(False, self.note.strip())
        return {'type': 'ir.actions.act_window_close'}
