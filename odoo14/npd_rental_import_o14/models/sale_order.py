# -*- coding: utf-8 -*-
"""ธงบอกว่าใบนี้ยกมาจาก Odoo 14 ไม่ได้สร้างบนฝั่ง 18"""
from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    o14_imported = fields.Boolean(
        string='ยกมาจาก Odoo 14', readonly=True, copy=False, index=True,
        help='ใบที่ยกข้อมูลมาตอนย้ายระบบ ไม่ใช่ใบที่สร้างบนฝั่ง 18 '
             'ใช้แยกตอนตรวจยอดและตอนคิดค่าคอม')
    o14_source_db = fields.Char(
        string='ฐานต้นทาง', readonly=True, copy=False,
        help='ชื่อฐานข้อมูลฝั่ง 14 ที่ใบนี้ถูกยกมา')
    o14_order_name = fields.Char(
        string='เลขใบฝั่ง 14', readonly=True, copy=False, index=True)
    o14_order_id = fields.Integer(
        string='id ฝั่ง 14', readonly=True, copy=False)

    # ---- ใบแจ้งหนี้/การชำระของใบนี้ฝั่ง 14 (ยกมาตอนย้ายระบบ) ----
    # ใบที่ฝั่ง 14 ออกใบแจ้งหนี้ไปแล้วและลูกค้าชำระบางส่วน ยกมาฝั่ง 18 แล้ว
    # ใบแจ้งหนี้ที่สร้างจากใบนี้ต้องเป็น "ยอดค้าง" เท่านั้น ไม่ใช่ยอดเต็มซ้ำ
    npd_o14_invoice_refs = fields.Char(
        string='ใบแจ้งหนี้ฝั่ง 14', readonly=True, copy=False)
    npd_o14_invoiced_total = fields.Monetary(
        string='ยอดออกใบแจ้งหนี้ฝั่ง 14', readonly=True, copy=False,
        currency_field='currency_id')
    npd_o14_paid_amount = fields.Monetary(
        string='ชำระแล้วในระบบเดิม', readonly=True, copy=False,
        currency_field='currency_id',
        help='ยอดที่ลูกค้าชำระ/ลดหนี้ไปแล้วในฝั่ง 14 (รวม VAT) '
             'ตอนสร้างใบแจ้งหนี้จากใบนี้ ระบบหักยอดนี้ออก ให้เหลือเฉพาะยอดค้าง')
    npd_o14_outstanding = fields.Monetary(
        string='ยอดค้างจากระบบเดิม', readonly=True, copy=False,
        currency_field='currency_id',
        help='ยอดที่ลูกค้ายังต้องจ่ายของใบนี้ = ส่วนที่ยังไม่ออกใบแจ้งหนี้ + ยอดค้างของใบแจ้งหนี้ฝั่ง 14')
    npd_o14_deduct_done = fields.Boolean(
        string='หักยอดชำระเดิมแล้ว', compute='_compute_npd_o14_deduct_done')

    def _compute_npd_o14_deduct_done(self):
        Line = self.env['account.move.line'].sudo()
        for order in self:
            order.npd_o14_deduct_done = bool(order.id) and bool(Line.search_count([
                ('npd_o14_deduct_order_id', '=', order.id), ('parent_state', '!=', 'cancel')]))

    def _create_invoices(self, *args, **kwargs):
        # ชำระครบแล้วในระบบเดิม ไม่มียอดให้ออกใบแจ้งหนี้อีก
        for order in self:
            if order.npd_o14_paid_amount > 0.005 and not order.npd_o14_deduct_done \
                    and order.npd_o14_outstanding <= 0.005:
                raise UserError(_(
                    'ใบ %(so)s ลูกค้าชำระครบแล้วในระบบเดิม (%(refs)s) ไม่มียอดค้างให้ออกใบแจ้งหนี้'
                ) % {'so': order.name, 'refs': order.npd_o14_invoice_refs or '-'})
        moves = super()._create_invoices(*args, **kwargs)
        for move in moves:
            orders = move.invoice_line_ids.sale_line_ids.order_id
            for order in orders.filtered(lambda o: o.npd_o14_paid_amount > 0.005 and not o.npd_o14_deduct_done):
                order._npd_add_o14_deduction(move)
        return moves

    def _npd_add_o14_deduction(self, move):
        """เพิ่มบรรทัดหักยอดที่ชำระแล้วในระบบเดิม ให้ยอดใบแจ้งหนี้ = ยอดค้าง

        ภาษีใช้ชุดเดียวกับบรรทัดของใบนี้ (VAT ของส่วนที่ชำระแล้วออกใบกำกับไปแล้วในฝั่ง 14)
        ปรับราคาบรรทัดหักทีละสตางค์จนยอดรวมตรงเป้า (กันเศษปัดของ VAT)
        """
        self.ensure_one()
        own = move.invoice_line_ids.filtered(lambda l: l.sale_line_ids.order_id == self and l.display_type == 'product')
        if not own:
            return
        ref = own[:1]
        taxes = ref.tax_ids
        rate = sum(t.amount for t in taxes if t.amount_type == 'percent' and not t.price_include) / 100.0
        target_total = move.amount_total - self.npd_o14_paid_amount
        price = -round(self.npd_o14_paid_amount / (1.0 + rate), 2)
        move.write({'invoice_line_ids': [(0, 0, {
            'name': _('หักยอดที่ชำระแล้วในระบบเดิม (%s)') % (self.npd_o14_invoice_refs or self.name),
            'quantity': 1,
            'price_unit': price,
            'account_id': ref.account_id.id,
            'tax_ids': [(6, 0, taxes.ids)],
            'analytic_distribution': ref.analytic_distribution,
            'npd_o14_deduct_order_id': self.id,
        })]})
        line = move.invoice_line_ids.filtered(lambda l: l.npd_o14_deduct_order_id == self)[:1]
        for _i in range(5):
            diff = round(move.amount_total - target_total, 2)
            if abs(diff) < 0.005:
                break
            step = 0.01 if diff < 0 else -0.01
            line.write({'price_unit': round(line.price_unit + step, 2)})
        move.message_post(body=_(
            'หักยอดที่ชำระแล้วในระบบเดิม %(paid)s (%(refs)s) จากใบ %(so)s คงเหลือยอดค้าง %(left)s'
        ) % {'paid': '{:,.2f}'.format(self.npd_o14_paid_amount), 'refs': self.npd_o14_invoice_refs or '-',
             'so': self.name, 'left': '{:,.2f}'.format(move.amount_total)})


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    npd_o14_deduct_order_id = fields.Many2one(
        'sale.order', string='หักยอดชำระเดิมของใบ', readonly=True, copy=False, index=True,
        ondelete='set null',
        help='บรรทัดหักยอดที่ลูกค้าชำระแล้วในระบบเดิม (ใบที่ยกมาจาก Odoo 14)')
