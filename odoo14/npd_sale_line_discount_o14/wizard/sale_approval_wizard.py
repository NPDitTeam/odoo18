# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class NpdSaleApprovalRequest(models.TransientModel):
    """พนักงานขายส่งขออนุมัติ — เห็นว่าใบติดเรื่องอะไร ส่งเฉพาะเรื่องที่ยังไม่อนุมัติ"""
    _name = 'npd.sale.approval.request'
    _description = 'ส่งขออนุมัติใบเสนอราคา'

    order_id = fields.Many2one('sale.order', required=True, readonly=True)
    approver_id = fields.Many2one(
        'res.users', string='ผู้อนุมัติ', required=True,
        domain="[('share', '=', False)]")
    note = fields.Text(string='เหตุผลที่ขออนุมัติ', required=True)
    summary = fields.Html(string='เรื่องที่ต้องอนุมัติ', compute='_compute_summary', sanitize=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env['sale.order'].browse(res.get('order_id') or self.env.context.get('default_order_id'))
        if order and order.approver_id and 'approver_id' in fields_list:
            res['approver_id'] = order.approver_id.id
        return res

    @api.depends('order_id')
    def _compute_summary(self):
        for wiz in self:
            order = wiz.order_id
            states = {'disc': order.npd_disc_appr, 'ins': order.npd_ins_appr}
            wiz.summary = order._npd_items_html(states={k: v for k, v in states.items() if v == 'approved'})

    def action_send(self):
        self.ensure_one()
        order = self.order_id
        items = order._npd_approval_items()
        pending = [(k, l, d) for k, l, d in items
                   if order['npd_%s_appr' % k] != 'approved']
        if not pending:
            raise UserError(_('ใบนี้ไม่มีเรื่องที่ต้องขออนุมัติแล้ว'))
        order.write({
            'approver_id': self.approver_id.id,
            'note_approver': self.note,
            'npd_appr_requester_id': self.env.user.id,
            **{'npd_%s_appr' % k: 'waiting' for k, _l, _d in pending},
        })
        order._npd_sync_state_sale()
        order._npd_close_approval_activity(_('ส่งขออนุมัติใหม่'))
        note = Markup('<p>%s</p>%s') % (self.note, order._npd_items_html(pending))
        order.activity_schedule(
            'mail.mail_activity_data_todo', user_id=self.approver_id.id,
            summary=_('ขออนุมัติ %s: %s') % (order.name, ', '.join(l for _k, l, _d in pending)),
            note=note)
        order.message_post(body=Markup('<p>ส่งขออนุมัติถึง <b>%s</b></p>%s') % (self.approver_id.name, note))
        return {'type': 'ir.actions.act_window_close'}


class NpdSaleApprovalDecide(models.TransientModel):
    """ผู้อนุมัติพิจารณาแยกเรื่อง อนุมัติ/ไม่อนุมัติ ทีละเรื่อง"""
    _name = 'npd.sale.approval.decide'
    _description = 'พิจารณาอนุมัติใบเสนอราคา'

    order_id = fields.Many2one('sale.order', required=True, readonly=True)
    request_note = fields.Text(string='เหตุผลที่ขอ', related='order_id.note_approver')
    requester_id = fields.Many2one(related='order_id.npd_appr_requester_id', string='ผู้ขออนุมัติ')
    line_ids = fields.One2many('npd.sale.approval.decide.line', 'wizard_id', string='เรื่องที่ต้องพิจารณา')
    note = fields.Text(string='หมายเหตุผู้อนุมัติ')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env['sale.order'].browse(res.get('order_id') or self.env.context.get('default_order_id'))
        if order and 'line_ids' in fields_list:
            res['line_ids'] = [
                (0, 0, {'kind': k, 'name': l, 'detail': d, 'decision': 'approve'})
                for k, l, d in order._npd_approval_items()
                if order['npd_%s_appr' % k] == 'waiting']
        return res

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        if order.approver_id != self.env.user:
            raise UserError(_('ใบนี้ส่งให้ %s อนุมัติ') % order.approver_id.name)
        if not self.line_ids:
            raise UserError(_('ไม่มีเรื่องที่รออนุมัติ'))
        if any(l.decision == 'reject' for l in self.line_ids) and not self.note:
            raise UserError(_('กรุณากรอกหมายเหตุ บอกเหตุผลที่ไม่อนุมัติ'))
        # ผู้อนุมัติอาจอยู่คนละสาขากับใบ (กฎสาขาห้ามเขียน) — ตรวจตัวคนแล้วข้างบน จึงบันทึกผลด้วย sudo
        # (sudo ไม่เปลี่ยนผู้ใช้ ข้อความในแชทยังเป็นชื่อผู้อนุมัติ)
        order = order.sudo()
        order.write({'npd_%s_appr' % l.kind: 'approved' if l.decision == 'approve' else 'rejected'
                     for l in self.line_ids})
        order._npd_sync_state_sale()
        result = ', '.join('%s: %s' % (l.name, 'อนุมัติ' if l.decision == 'approve' else 'ไม่อนุมัติ')
                           for l in self.line_ids)
        order._npd_close_approval_activity(result)
        order._npd_notify_requester(result + (' — %s' % self.note if self.note else ''))
        return {'type': 'ir.actions.act_window_close'}

    def action_approve_all(self):
        self.line_ids.write({'decision': 'approve'})
        return self.action_confirm()


class NpdSaleApprovalDecideLine(models.TransientModel):
    _name = 'npd.sale.approval.decide.line'
    _description = 'เรื่องที่พิจารณาอนุมัติ'

    wizard_id = fields.Many2one('npd.sale.approval.decide', required=True, ondelete='cascade')
    kind = fields.Selection([('disc', 'ส่วนลดสินค้า'), ('ins', 'ค่าประกัน')], required=True)
    name = fields.Char(string='เรื่อง', readonly=True)
    detail = fields.Text(string='รายละเอียด', readonly=True)
    decision = fields.Selection(
        [('approve', 'อนุมัติ'), ('reject', 'ไม่อนุมัติ')], string='ผลพิจารณา',
        required=True, default='approve')
