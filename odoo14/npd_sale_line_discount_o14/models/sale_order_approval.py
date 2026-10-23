# -*- coding: utf-8 -*-
"""อนุมัติใบเสนอราคาแยกเรื่อง: ส่วนลดสินค้า / ค่าประกัน (ผู้ใช้สั่ง 23 ต.ค. 2569)

เดิม (o14 และ o18) ใบหนึ่งมีสถานะอนุมัติช่องเดียว (state_sale) กด Approve ครั้งเดียวผ่านทุกเรื่อง
ผู้อนุมัติไม่เห็นว่าติดเรื่องอะไร และอนุมัติเรื่องหนึ่ง/ไม่อนุมัติอีกเรื่องไม่ได้

- เก็บสถานะแยก 2 เรื่อง แล้วคำนวณ state_sale จากสองเรื่องนี้ (ปุ่ม/ป้ายเดิมทำงานต่อได้)
- แก้ตัวเลขของเรื่องไหนหลังส่ง/อนุมัติแล้ว เรื่องนั้นต้องขอใหม่
- ใช้กับใบเสนอราคา (draft/sent) เท่านั้น ขออนุมัติส่วนลดค่าเช่าหลังยืนยันใบ (_r) ยังเป็นแบบเดิม
"""
from markupsafe import Markup, escape

from odoo import _, api, fields, models

APPROVAL_STATES = [
    ('waiting', 'รออนุมัติ'),
    ('approved', 'อนุมัติแล้ว'),
    ('rejected', 'ไม่อนุมัติ'),
]
ITEM_LABELS = {'disc': 'ส่วนลดสินค้า', 'ins': 'ค่าประกัน'}
DISC_FIELDS = ('discount_amount', 'discount_method', 'discount_type_selection')
INS_FIELDS = ('pfb_required_insurance_premium', 'pfb_dis_amount_insurance')


def _baht(value):
    return '{:,.2f}'.format(value or 0.0)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    npd_disc_appr = fields.Selection(APPROVAL_STATES, string='อนุมัติส่วนลดสินค้า', copy=False, tracking=True)
    npd_ins_appr = fields.Selection(APPROVAL_STATES, string='อนุมัติค่าประกัน', copy=False, tracking=True)
    npd_appr_requester_id = fields.Many2one('res.users', string='ผู้ขออนุมัติ', copy=False)
    npd_disc_need = fields.Boolean(string='ส่วนลดต้องอนุมัติ', compute='_compute_npd_disc_need')
    npd_ins_need = fields.Boolean(string='ค่าประกันต้องอนุมัติ', compute='_compute_npd_ins_need')

    # ------------------------------------------------------------------ เงื่อนไข
    def _npd_disc_issue_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: l.product_id and l.discount_amount
            and l.discount_type_selection in (False, 'product')
            and l._npd_discount_baht() > l.price_subtotal_without_discount * 0.5)

    @api.depends('order_line.discount_amount', 'order_line.discount_method',
                 'order_line.discount_type_selection', 'order_line.price_unit',
                 'order_line.product_uom_qty', 'order_line.tax_id')
    def _compute_npd_disc_need(self):
        for order in self:
            order.npd_disc_need = bool(order._npd_disc_issue_lines())

    def _npd_ins_below_min(self):
        self.ensure_one()
        return (self.pfb_amount_insurance > 0 and self.pfb_dis_amount_insurance > 0
                and self.pfb_amount < self.pfb_insurance_min)

    @api.depends('pfb_amount_insurance', 'pfb_dis_amount_insurance', 'pfb_amount', 'pfb_insurance_min')
    def _compute_npd_ins_need(self):
        for order in self:
            order.npd_ins_need = order._npd_ins_below_min() or order._npd_insurance_over_full()

    def _npd_is_quotation(self):
        self.ensure_one()
        return self.state in ('draft', 'sent')

    def _npd_approval_items(self):
        """เรื่องที่ใบนี้ต้องอนุมัติ: [(kind, หัวข้อ, รายละเอียด)]"""
        self.ensure_one()
        items = []
        if self.npd_disc_need:
            rows = []
            for line in self._npd_disc_issue_lines():
                gross = line.price_subtotal_without_discount
                baht = line._npd_discount_baht()
                pct = baht / gross * 100 if gross else 0.0
                rows.append(_('%(p)s: ลด %(b)s บาท (%(pct)s%%) เกินเกณฑ์ 50%% = %(m)s บาท') % {
                    'p': line.product_id.display_name, 'b': _baht(baht),
                    'pct': '{:,.2f}'.format(pct), 'm': _baht(gross * 0.5)})
            items.append(('disc', ITEM_LABELS['disc'], '\n'.join(rows)))
        if self.npd_ins_need:
            want = self.pfb_amount
            if self._npd_insurance_over_full():
                detail = _('ค่าประกันที่ต้องการ %(w)s บาท เกินค่าประกันสินค้า %(f)s บาท') % {
                    'w': _baht(want), 'f': _baht(self.pfb_amount_insurance)}
            else:
                detail = _('ค่าประกันที่ต้องการ %(w)s บาท ต่ำกว่าขั้นต่ำ %(m)s บาท (15%% ของ %(f)s บาท)') % {
                    'w': _baht(want), 'm': _baht(self.pfb_insurance_min),
                    'f': _baht(self.pfb_amount_insurance)}
            items.append(('ins', ITEM_LABELS['ins'], detail))
        return items

    def _npd_items_html(self, items=None, states=None):
        self.ensure_one()
        items = self._npd_approval_items() if items is None else items
        parts = []
        for kind, label, detail in items:
            state = (states or {}).get(kind)
            head = escape(label) + (Markup(' — <b>%s</b>') % dict(APPROVAL_STATES)[state] if state else '')
            parts.append(Markup('<li>%s<br/>%s</li>') % (head, Markup('<br/>').join(escape(detail).split('\n'))))
        return Markup('<ul>%s</ul>') % Markup('').join(parts) if parts else ''

    # ------------------------------------------------------------------ สถานะรวม
    def _npd_sync_state_sale(self):
        for order in self:
            if not order._npd_is_quotation():
                continue
            states = []
            if order.npd_disc_need:
                states.append(order.npd_disc_appr)
            if order.npd_ins_need:
                states.append(order.npd_ins_appr)
            if not states:
                new = 'draft' if order.state_sale in ('waiting_to_approve', 'reject') else order.state_sale
            elif 'rejected' in states:
                new = 'reject'
            elif all(s == 'approved' for s in states):
                new = 'approved'
            elif 'waiting' in states:
                new = 'waiting_to_approve'
            else:
                new = 'draft'
            if new != order.state_sale:
                super(SaleOrder, order).write({'state_sale': new})

    def write(self, vals):
        # แก้ค่าประกันหลังส่ง/อนุมัติแล้ว → เรื่องค่าประกันต้องขอใหม่
        # และคิดสถานะรวมใหม่ทุกครั้ง: อนุมัติส่วนลดไปแล้ว แล้วเพิ่งกรอกค่าประกันต่ำกว่าขั้นต่ำทีหลัง
        # ต้องกลับไปขออนุมัติ (ไม่งั้นค้าง "อนุมัติแล้ว" กด Convert ได้)
        changed = self.browse()
        if any(f in vals for f in INS_FIELDS):
            changed = self.filtered(lambda o: o._npd_is_quotation() and any(
                f in vals and o[f] != vals[f] for f in INS_FIELDS))
        res = super().write(vals)
        if changed:
            reset = changed.filtered('npd_ins_appr')
            if reset:
                super(SaleOrder, reset).write({'npd_ins_appr': False})
            changed._npd_sync_state_sale()
        return res

    def action_draft(self):
        res = super().action_draft()
        self.filtered(lambda o: o.state == 'draft').write({'npd_disc_appr': False, 'npd_ins_appr': False})
        return res

    # ------------------------------------------------------------------ ปุ่ม
    def _npd_split_flow(self):
        return len(self) == 1 and self._npd_is_quotation() and (self.npd_disc_need or self.npd_ins_need)

    def action_waiting_to_approve(self):
        if not self._npd_split_flow():
            return super().action_waiting_to_approve()
        return {
            'type': 'ir.actions.act_window',
            'name': _('ส่งขออนุมัติ'),
            'res_model': 'npd.sale.approval.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_open_approval_popup(self):
        if not (len(self) == 1 and self._npd_is_quotation() and 'waiting' in (self.npd_disc_appr, self.npd_ins_appr)):
            return super().action_open_approval_popup()
        return {
            'type': 'ir.actions.act_window',
            'name': _('พิจารณาอนุมัติ %s') % self.name,
            'res_model': 'npd.sale.approval.decide',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_reject(self):
        split = self.filtered(lambda o: o._npd_is_quotation() and 'waiting' in (o.npd_disc_appr, o.npd_ins_appr))
        for order in split:
            vals = {f: 'rejected' for f in ('npd_disc_appr', 'npd_ins_appr') if order[f] == 'waiting'}
            super(SaleOrder, order).write(vals)
            order._npd_sync_state_sale()
            order._npd_close_approval_activity(_('ไม่อนุมัติทั้งหมด'))
            order._npd_notify_requester(_('ไม่อนุมัติ'))
        rest = self - split
        return super(SaleOrder, rest).action_reject() if rest else True

    def _compute_button_visible_reject(self):
        # เดิมทุกคนเห็นปุ่ม Reject — ให้เห็นเฉพาะผู้อนุมัติของใบ
        for order in self:
            order.button_visible_reject = (
                order.state_sale == 'waiting_to_approve' and order.approver_id.id == self.env.uid)

    # ------------------------------------------------------------------ แจ้งเตือน
    def _npd_close_approval_activity(self, feedback):
        activities = self.activity_ids.filtered(
            lambda a: a.summary and a.summary.startswith('ขออนุมัติ'))
        if activities:
            activities.action_feedback(feedback=feedback)

    def _npd_notify_requester(self, result_text):
        self.ensure_one()
        partner = self.npd_appr_requester_id.partner_id
        body = Markup('<p>ผลการพิจารณาอนุมัติ: <b>%s</b></p>%s') % (
            result_text, self._npd_items_html(states={'disc': self.npd_disc_appr, 'ins': self.npd_ins_appr}))
        self.message_post(body=body, partner_ids=partner.ids, subtype_xmlid='mail.mt_comment')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _npd_reset_disc_approval(self, orders):
        orders = orders.filtered(lambda o: o._npd_is_quotation())
        reset = orders.filtered('npd_disc_appr')
        if reset:
            super(SaleOrder, reset).write({'npd_disc_appr': False})
        orders._npd_sync_state_sale()

    def write(self, vals):
        # แก้ส่วนลดหลังส่ง/อนุมัติแล้ว → เรื่องส่วนลดต้องขอใหม่
        changed = self.env['sale.order']
        if any(f in vals for f in DISC_FIELDS):
            changed = self.filtered(lambda l: any(f in vals and l[f] != vals[f] for f in DISC_FIELDS)).order_id
        res = super().write(vals)
        self._npd_reset_disc_approval(changed)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self._npd_reset_disc_approval(lines.filtered('discount_amount').order_id)
        return lines

    def unlink(self):
        orders = self.filtered('discount_amount').order_id
        res = super().unlink()
        self._npd_reset_disc_approval(orders.exists())
        return res
