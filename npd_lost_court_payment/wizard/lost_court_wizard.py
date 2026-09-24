# -*- coding: utf-8 -*-
"""หน้าต่างปรับใบค่าปรับหายให้เท่ายอดงวดที่ศาลสั่ง

ของเดิมบัญชีออกใบทีละงวด โดยกรอกยอดค้างเต็มมาทั้งใบ แล้วไล่ทำส่วนลดรายบรรทัด
เองจนเหลือเท่ายอดงวดนั้น หน้าต่างนี้แทนงานมือตรงนั้น — ระบุยอดงวดเดียว ระบบเลือก
จำนวนสินค้าให้ยอดรวมใกล้ที่สุดโดยไม่ต่ำกว่า เหลือเศษเท่าไรค่อยทำส่วนลดต่อ
"""
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

from odoo.addons.npd_lost_court_payment.models.account_move import solve_quantities

_logger = logging.getLogger(__name__)


def _fmt(value):
    return '{:,.2f}'.format(value or 0.0)


class LostCourtWizard(models.TransientModel):
    _name = 'npd.lost.court.wizard'
    _description = 'จ่ายค่าปรับหายตามศาล'

    move_id = fields.Many2one('account.move', string='ใบแจ้งหนี้',
                              required=True, readonly=True)
    move_name = fields.Char(related='move_id.name', string='เลขที่ใบ', readonly=True)
    partner_id = fields.Many2one(related='move_id.partner_id', string='ลูกค้า',
                                 readonly=True)
    invoice_total = fields.Float(string='ยอดสินค้าในใบตอนนี้', digits=(16, 2),
                                 readonly=True)
    product_summary = fields.Text(string='สินค้าในใบตอนนี้', readonly=True)

    installment_no = fields.Integer(string='งวดที่', default=1)
    court_amount = fields.Float(string='ยอดที่ศาลสั่งให้จ่ายงวดนี้', digits=(16, 2),
                                required=True)
    due_date = fields.Date(string='วันครบกำหนดของงวดนี้')
    court_note = fields.Text(string='หมายเหตุคำสั่งศาล')

    planned_amount = fields.Float(string='ยอดที่จัดได้', digits=(16, 2), readonly=True)
    diff_amount = fields.Float(string='เศษที่ต้องทำส่วนลดต่อ', digits=(16, 2),
                               readonly=True)
    qty_preview = fields.Text(string='จำนวนที่จะปรับเป็น', readonly=True)
    computed = fields.Boolean(default=False)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move_id = res.get('move_id') or self.env.context.get('default_move_id')
        if not move_id:
            return res
        move = self.env['account.move'].browse(move_id)
        lines = move.lost_court_lines()
        res['invoice_total'] = sum(l.price_unit * l.quantity for l in lines)
        res['product_summary'] = '\n'.join(
            '%s — %s x %s = %s' % (
                l.product_id.display_name or l.name or '-',
                _fmt(l.quantity), _fmt(l.price_unit),
                _fmt(l.price_unit * l.quantity))
            for l in lines)
        res['due_date'] = move.invoice_date_due or move.invoice_date
        if move.lost_court_installment_no:
            res['installment_no'] = move.lost_court_installment_no
        return res

    # ------------------------------------------------------------------
    def _solve(self):
        """เลือกจำนวนของแต่ละบรรทัดให้ยอดรวมไม่ต่ำกว่ายอดศาล และใกล้ที่สุด"""
        self.ensure_one()
        lines = self.move_id.lost_court_lines()
        if not lines:
            raise UserError('ใบนี้ไม่มีบรรทัดสินค้าที่มีราคาและจำนวน')
        if self.court_amount <= 0:
            raise UserError('กรุณาระบุยอดที่ศาลสั่งให้จ่ายงวดนี้')

        prices = [l.price_unit for l in lines]
        max_qty = []
        for line in lines:
            qty = int(round(line.quantity))
            if abs(line.quantity - qty) > 0.001:
                raise UserError(
                    'บรรทัด "%s" มีจำนวน %s ซึ่งไม่ใช่จำนวนเต็ม ระบบปรับให้ไม่ได้\n'
                    'กรุณาแก้จำนวนให้เป็นจำนวนเต็มก่อน'
                    % (line.product_id.display_name or line.name, line.quantity))
            max_qty.append(qty)

        picked, amount = solve_quantities(prices, max_qty, self.court_amount)
        if picked is None:
            raise UserError(
                'สินค้าในใบนี้รวมกันได้แค่ %s บาท ซึ่งไม่ถึงยอดที่ศาลสั่ง %s บาท\n'
                'ระบบจึงปรับจำนวนให้ไม่ได้ เพราะห้ามตั้งยอดต่ำกว่าที่ศาลสั่ง'
                % (_fmt(sum(p * q for p, q in zip(prices, max_qty))),
                   _fmt(self.court_amount)))
        return lines, picked, amount

    def action_preview(self):
        """ดูผลก่อน ยังไม่แตะใบจริง"""
        self.ensure_one()
        lines, picked, amount = self._solve()
        self.planned_amount = amount
        self.diff_amount = amount - self.court_amount
        rows = []
        for line, qty in zip(lines, picked):
            name = line.product_id.display_name or line.name or '-'
            if qty:
                rows.append('%s — %s ชิ้น x %s = %s%s' % (
                    name, _fmt(qty), _fmt(line.price_unit),
                    _fmt(qty * line.price_unit),
                    '' if qty == int(round(line.quantity))
                    else '  (เดิม %s)' % _fmt(line.quantity)))
            else:
                rows.append('%s — ตัดออกจากใบนี้ (เดิม %s ชิ้น)'
                            % (name, _fmt(line.quantity)))
        self.qty_preview = '\n'.join(rows)
        self.computed = True
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        """ปรับจำนวนในใบนี้จริง

        Odoo 18 คิด price_subtotal / บรรทัดภาษี เป็นฟิลด์คำนวณแบบเก็บค่า
        แค่เขียน quantity ระบบจะคิดยอดและบรรทัดภาษีใหม่ให้เอง ไม่ต้องสั่งเอง
        เหมือนฝั่ง Odoo 14
        """
        self.ensure_one()
        move = self.move_id
        if move.state != 'draft':
            raise UserError('ใบนี้ยืนยันแล้ว แก้จำนวนสินค้าไม่ได้ '
                            'ให้กลับไปเป็นร่างก่อน')
        lines, picked, amount = self._solve()

        before = '\n'.join(
            '%s %s ชิ้น' % (l.product_id.display_name or l.name or '-', _fmt(l.quantity))
            for l in lines)
        keep_partner = move.partner_id.id

        commands = []
        for line, qty in zip(lines, picked):
            if qty:
                if abs(line.quantity - qty) > 0.0001:
                    commands.append((1, line.id, {'quantity': qty}))
            else:
                commands.append((2, line.id))

        vals = {
            'lost_court_amount': self.court_amount,
            'lost_court_installment_no': self.installment_no or 1,
        }
        if commands:
            vals['invoice_line_ids'] = commands
        if self.due_date:
            vals['invoice_date_due'] = self.due_date
            vals['invoice_payment_term_id'] = False
        move.write(vals)

        # ฝั่ง Odoo 14 เคยเจอช่องลูกค้าหายตอนเขียนบรรทัด (บั๊กของโมดูลเสริมที่นั่น)
        # ที่นี่ยังไม่เจอ แต่ตรวจไว้กันพลาด ดีกว่าปล่อยใบที่ไม่มีลูกค้าไว้ในระบบ
        if keep_partner and not move.partner_id:
            raise UserError('ระบบปรับจำนวนแล้วแต่ช่องลูกค้าหายไป '
                            'ยกเลิกการแก้ไขเพื่อความปลอดภัย กรุณาแจ้งฝ่าย IT')

        body = ('ปรับจำนวนสินค้าตามคำสั่งศาล งวดที่ %s<br/>'
                'ยอดตามศาล %s บาท | ใบนี้ตั้งไว้ %s บาท | '
                'เศษที่ต้องทำส่วนลดต่อ %s บาท<br/>'
                '<b>จำนวนเดิมก่อนปรับ</b><br/>%s') % (
                   self.installment_no or 1, _fmt(self.court_amount),
                   _fmt(amount), _fmt(amount - self.court_amount),
                   before.replace('\n', '<br/>'))
        if (self.court_note or '').strip():
            body += '<br/><b>หมายเหตุ:</b> %s' % self.court_note.strip()
        move.message_post(body=body)

        return {'type': 'ir.actions.act_window_close'}
