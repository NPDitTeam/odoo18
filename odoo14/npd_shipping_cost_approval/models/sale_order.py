# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare

SHIP_APPROVAL_ACTIVITY_SUMMARY = 'ขออนุมัติค่าขนส่งพิเศษ'
SHIP_APPROVAL_WATCHED_FIELDS = ('use_special_delivery_zero', 'shipping_cost_m')
SHIP_APPROVAL_PERCENT_PARAM = 'npd_shipping_cost_approval.min_percent'
SHIP_APPROVAL_PERCENT_DEFAULT = 30.0


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    ship_approval_required = fields.Boolean(
        string='ต้องอนุมัติค่าขนส่ง',
        compute='_compute_ship_approval_required',
        help='ติ๊ก "ใช้ค่าขนส่งพิเศษที่เป็น 0" หรือ "ค่าขนส่งพิเศษ" ต่ำกว่า 30% ของค่าขนส่งหลังปัดเศษ '
             'ต้องขออนุมัติก่อนยืนยัน (ปรับ % ได้ที่ System Parameter npd_shipping_cost_approval.min_percent)',
    )
    ship_approval_state = fields.Selection(
        selection=[
            ('draft', 'ยังไม่ขออนุมัติ'),
            ('waiting', 'รออนุมัติ'),
            ('approved', 'อนุมัติแล้ว'),
            ('reject', 'ไม่อนุมัติ'),
        ],
        string='สถานะอนุมัติค่าขนส่ง',
        default='draft',
        readonly=True,
        copy=False,
        tracking=True,
    )
    ship_approver_id = fields.Many2one(
        'res.users', string='ผู้อนุมัติค่าขนส่ง', readonly=True, copy=False, tracking=True)
    ship_approval_reason = fields.Text(string='เหตุผลในการขออนุมัติ', readonly=True, copy=False)
    ship_request_user_id = fields.Many2one('res.users', string='ผู้ขออนุมัติค่าขนส่ง', readonly=True, copy=False)
    ship_request_date = fields.Datetime(string='วันที่ขออนุมัติค่าขนส่ง', readonly=True, copy=False)
    ship_approved_user_id = fields.Many2one(
        'res.users', string='ผู้พิจารณาค่าขนส่ง', readonly=True, copy=False,
        help='ผู้ที่กดอนุมัติ/ไม่อนุมัติจริง')
    ship_approved_date = fields.Datetime(string='วันที่พิจารณาค่าขนส่ง', readonly=True, copy=False)
    ship_approval_note = fields.Text(string='ความเห็นผู้อนุมัติ', readonly=True, copy=False)
    ship_approval_result = fields.Char(string='ผลการอนุมัติค่าขนส่ง', compute='_compute_ship_approval_result')
    ship_can_approve = fields.Boolean(compute='_compute_ship_can_approve')

    @api.model
    def _ship_min_percent(self):
        value = self.env['ir.config_parameter'].sudo().get_param(SHIP_APPROVAL_PERCENT_PARAM)
        try:
            return float(value) if value else SHIP_APPROVAL_PERCENT_DEFAULT
        except ValueError:
            return SHIP_APPROVAL_PERCENT_DEFAULT

    @api.depends('use_special_delivery_zero', 'shipping_cost_m', 'shipping_cost')
    def _compute_ship_approval_required(self):
        percent = self._ship_min_percent()
        for order in self:
            special = order.shipping_cost_m or 0.0
            threshold = (order.shipping_cost or 0.0) * percent / 100.0
            order.ship_approval_required = bool(
                order.use_special_delivery_zero
                or (float_compare(special, 0.0, precision_digits=2) > 0
                    and float_compare(special, threshold, precision_digits=2) < 0)
            )

    @api.depends('ship_approval_state', 'ship_approver_id', 'ship_approved_user_id', 'ship_approved_date')
    def _compute_ship_approval_result(self):
        for order in self:
            state = order.ship_approval_state
            if state == 'waiting':
                result = _('รออนุมัติจาก %s') % order.ship_approver_id.name
            elif state == 'approved' and not order.ship_approved_user_id:
                result = _('อนุมัติแล้ว (ใบที่มีก่อนเปิดใช้ระบบอนุมัติ)')
            elif state in ('approved', 'reject'):
                date_str = ''
                if order.ship_approved_date:
                    date_str = fields.Datetime.context_timestamp(
                        order, order.ship_approved_date).strftime('%d/%m/%Y %H:%M')
                label = _('อนุมัติแล้ว') if state == 'approved' else _('ไม่อนุมัติ')
                result = _('%s โดย %s เมื่อ %s') % (label, order.ship_approved_user_id.name, date_str)
            else:
                result = _('ยังไม่ขออนุมัติ')
            order.ship_approval_result = result

    @api.depends('ship_approval_state', 'ship_approver_id')
    @api.depends_context('uid')
    def _compute_ship_can_approve(self):
        for order in self:
            order.ship_can_approve = (
                order.ship_approval_state == 'waiting' and order.ship_approver_id.id == self.env.uid
            )

    # ---------------------------------------------------------------- buttons

    def _ship_open_wizard(self, mode):
        self.ensure_one()
        titles = {
            'request': _('ขออนุมัติค่าขนส่งพิเศษ'),
            'approve': _('อนุมัติค่าขนส่งพิเศษ'),
            'reject': _('ไม่อนุมัติค่าขนส่งพิเศษ'),
        }
        return {
            'type': 'ir.actions.act_window',
            'name': titles[mode],
            'res_model': 'shipping.cost.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sale_order_id': self.id, 'default_mode': mode},
        }

    def action_ship_request_approval(self):
        self.ensure_one()
        if not self.ship_approval_required:
            raise UserError(_('ใบนี้ไม่ได้ใช้ค่าขนส่งพิเศษ ไม่ต้องขออนุมัติ'))
        if self.ship_approval_state not in ('draft', 'reject'):
            raise UserError(_('ใบนี้ส่งขออนุมัติค่าขนส่งไปแล้ว'))
        return self._ship_open_wizard('request')

    def action_ship_approve(self):
        self._ship_check_approver()
        return self._ship_open_wizard('approve')

    def action_ship_reject(self):
        self._ship_check_approver()
        return self._ship_open_wizard('reject')

    def _ship_check_approver(self):
        self.ensure_one()
        if self.ship_approval_state != 'waiting':
            raise UserError(_('ใบนี้ไม่ได้อยู่ในสถานะรออนุมัติค่าขนส่ง'))
        if self.ship_approver_id.id != self.env.uid:
            raise UserError(_('เฉพาะ %s เท่านั้นที่อนุมัติค่าขนส่งของใบนี้ได้') % self.ship_approver_id.name)
        if not self.env.user.has_group('npd_shipping_cost_approval.group_ship_cost_approver'):
            raise UserError(_('คุณไม่มีสิทธิ์ "ผู้อนุมัติค่าขนส่งพิเศษ" แล้ว กรุณาให้ผู้ขอส่งขออนุมัติใหม่'))

    # ------------------------------------------------------------ workflow

    def _ship_do_request(self, approver, reason):
        for order in self:
            order._ship_close_activities()
            order.write({
                'ship_approval_state': 'waiting',
                'ship_approver_id': approver.id,
                'ship_approval_reason': reason,
                'ship_request_user_id': self.env.uid,
                'ship_request_date': fields.Datetime.now(),
                'ship_approved_user_id': False,
                'ship_approved_date': False,
                'ship_approval_note': False,
            })
            order.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=SHIP_APPROVAL_ACTIVITY_SUMMARY,
                note=reason,
                user_id=approver.id,
            )
            order.message_post(body=_(
                'ขออนุมัติค่าขนส่งพิเศษ (%s) ถึง %s<br/>เหตุผล: %s'
            ) % (order._ship_value_label(), approver.name, reason))

    def _ship_do_decide(self, approved, note):
        for order in self:
            order._ship_check_approver()
            order.write({
                'ship_approval_state': 'approved' if approved else 'reject',
                'ship_approved_user_id': self.env.uid,
                'ship_approved_date': fields.Datetime.now(),
                'ship_approval_note': note,
            })
            order._ship_close_activities(feedback=note or '')
            label = _('อนุมัติ') if approved else _('ไม่อนุมัติ')
            body = _('%s ค่าขนส่งพิเศษ (%s)') % (label, order._ship_value_label())
            if note:
                body += _('<br/>ความเห็น: %s') % note
            order.message_post(body=body)

    def _ship_reset_approval(self):
        for order in self:
            order._ship_close_activities()
            order.write({
                'ship_approval_state': 'draft',
                'ship_approved_user_id': False,
                'ship_approved_date': False,
                'ship_approval_note': False,
            })
            order.message_post(body=_(
                'ค่าขนส่งพิเศษถูกแก้ไขเป็น (%s) ต้องขออนุมัติใหม่'
            ) % order._ship_value_label())

    def _ship_close_activities(self, feedback=False):
        activities = self.activity_ids.filtered(lambda a: a.summary == SHIP_APPROVAL_ACTIVITY_SUMMARY)
        if not activities:
            return
        if feedback is False:
            activities.sudo().unlink()
        else:
            activities.sudo().action_feedback(feedback=feedback or '')

    def _ship_value_label(self):
        self.ensure_one()
        if self.use_special_delivery_zero:
            return _('ใช้ค่าขนส่งพิเศษที่เป็น 0')
        return _('ค่าขนส่งพิเศษ %s บาท จากค่าขนส่งหลังปัดเศษ %s บาท') % (
            '{:,.2f}'.format(self.shipping_cost_m or 0.0), '{:,.2f}'.format(self.shipping_cost or 0.0))

    def _ship_values(self):
        self.ensure_one()
        return (bool(self.use_special_delivery_zero), round(self.shipping_cost_m or 0.0, 2))

    # ------------------------------------------------------------- overrides

    def write(self, vals):
        if self.env.context.get('skip_ship_approval_reset') or not any(
                f in vals for f in SHIP_APPROVAL_WATCHED_FIELDS):
            return super().write(vals)
        before = {order.id: order._ship_values() for order in self}
        res = super().write(vals)
        changed = self.filtered(
            lambda o: o.ship_approval_state != 'draft' and o._ship_values() != before[o.id])
        if changed:
            changed.with_context(skip_ship_approval_reset=True)._ship_reset_approval()
        return res

    def copy(self, default=None):
        default = dict(default or {})
        # ใบเสนอราคา -> Convert to Order (sale_isolated_quotation) ใช้ copy() พร้อม quote_id
        # ให้ผลอนุมัติติดไปที่ใบสั่งขายด้วย ส่วนการ Duplicate ปกติต้องขออนุมัติใหม่
        if default.get('quote_id') and len(self) == 1:
            for fname in ('ship_approval_state', 'ship_approver_id', 'ship_approval_reason',
                          'ship_request_user_id', 'ship_request_date', 'ship_approved_user_id',
                          'ship_approved_date', 'ship_approval_note'):
                default.setdefault(fname, self._fields[fname].convert_to_write(self[fname], self))
        return super().copy(default)

    def action_confirm(self):
        for order in self:
            if order.ship_approval_required and order.ship_approval_state != 'approved':
                state_label = dict(self._fields['ship_approval_state'].selection)[order.ship_approval_state]
                raise UserError(_(
                    '%s ใช้ค่าขนส่งพิเศษ (%s) ต้องได้รับการอนุมัติก่อนยืนยัน\n'
                    'สถานะปัจจุบัน: %s\n'
                    'กดปุ่ม "ขออนุมัติค่าขนส่ง" แล้วรอผู้อนุมัติกดอนุมัติ'
                ) % (order.name, order._ship_value_label(), state_label))
        return super().action_confirm()
