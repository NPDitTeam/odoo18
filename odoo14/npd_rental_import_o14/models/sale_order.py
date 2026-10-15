# -*- coding: utf-8 -*-
"""ธงบอกว่าใบนี้ยกมาจาก Odoo 14 ไม่ได้สร้างบนฝั่ง 18"""
import json

from odoo import _, api, fields, models
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
        help='ยอดที่ลูกค้ายังต้องจ่ายของใบนี้ทุกประเภท (ใบหลัก + ใบประเภทอื่นที่ค้าง)')
    npd_o14_main_outstanding = fields.Monetary(
        string='ยอดค้างใบหลัก', readonly=True, copy=False, currency_field='currency_id',
        help='ยอดค้างของใบแจ้งหนี้ที่ออกจากบรรทัดใบเช่า + ส่วนที่ยังไม่ออกใบ')
    npd_o14_open_others = fields.Text(
        string='ใบประเภทอื่นที่ค้าง (ฝั่ง 14)', readonly=True, copy=False,
        help='ใบเพิ่มหนี้ เช่น ค่าเช่าส่วนต่าง / สินค้าหาย / ชำรุด ที่ยังค้าง ออกแยกใบตามประเภทเดิม')
    npd_o14_reissued = fields.Boolean(
        string='ออกใบแจ้งหนี้ยอดค้างแล้ว', readonly=True, copy=False)

    def _npd_o14_others(self):
        self.ensure_one()
        try:
            return json.loads(self.npd_o14_open_others or '[]')
        except ValueError:
            return []

    def _npd_o14_active_reissue(self):
        """ใบแจ้งหนี้ยอดค้างที่ออกจากใบนี้แล้ว และยังไม่ถูกยกเลิก"""
        self.ensure_one()
        return self.env['account.move'].sudo().search([
            ('npd_o14_reissue_order_id', '=', self.id), ('state', '!=', 'cancel')])

    @api.depends('order_line.invoice_lines', 'npd_o14_reissued')
    def _get_invoiced(self):
        """ปุ่ม "ใบแจ้งหนี้" บนใบสั่งขาย นับรวมใบยอดค้างประเภทอื่นที่ออกจากใบนี้
        (ใบค่าเช่าส่วนต่าง / สินค้าหาย ฯลฯ ไม่ได้ผูกกับบรรทัดใบเช่า ระบบเดิมจึงมองไม่เห็น)"""
        super()._get_invoiced()
        Move = self.env['account.move'].sudo()
        for order in self.filtered(lambda o: o.id and o.npd_o14_reissued):
            extra = Move.search([('npd_o14_reissue_order_id', '=', order.id)])
            if extra:
                order.invoice_ids = (order.invoice_ids | extra.with_env(self.env)).ids
                order.invoice_count = len(order.invoice_ids)

    @api.depends('state', 'order_line.invoice_status', 'npd_o14_reissued')
    def _compute_invoice_status(self):
        super()._compute_invoice_status()
        # ใบหลักชำระครบในระบบเดิม ออกแค่ใบประเภทอื่น → ไม่มีอะไรให้ออกจากใบนี้อีก
        for order in self:
            if order.npd_o14_reissued and order.invoice_status == 'to invoice':
                order.invoice_status = 'invoiced'

    def _create_invoices(self, *args, **kwargs):
        """ใบที่ยกมาจาก o14 และมีใบแจ้งหนี้ฝั่ง 14 แล้ว → ออกเฉพาะยอดค้าง แยกใบตามประเภทเดิม

        * ใบหลัก (ออกจากบรรทัดใบเช่า) → สร้างจากใบสั่งขายตามปกติ แล้วหักยอดที่ชำระแล้ว
        * ใบประเภทอื่นที่ค้าง (ค่าเช่าส่วนต่าง / สินค้าหาย / ชำรุด ฯลฯ) → ใบละประเภท ยอด = ยอดค้างของใบนั้น
        """
        o14 = self.filtered(lambda o: o.npd_o14_invoice_refs)
        moves = super(SaleOrder, self - o14)._create_invoices(*args, **kwargs) if self - o14 \
            else self.env['account.move']
        for order in o14:
            done = order._npd_o14_active_reissue()
            if done:
                raise UserError(_(
                    'ใบ %(so)s ออกใบแจ้งหนี้ยอดค้างจากระบบเดิมไปแล้ว: %(moves)s\n'
                    'ถ้าต้องการออกใหม่ ให้ยกเลิกใบเดิมก่อน'
                ) % {'so': order.name, 'moves': ', '.join(done.mapped(lambda m: m.name or '(ร่าง)'))})
            part = self.env['account.move']
            if order.npd_o14_main_outstanding > 0.005:
                main = super(SaleOrder, order)._create_invoices(*args, **kwargs)
                for move in main:
                    if order.npd_o14_paid_amount > 0.005:
                        order._npd_add_o14_deduction(move)
                    move.npd_o14_reissue_order_id = order
                part |= main
            for other in order._npd_o14_others():
                part |= order._npd_create_o14_other_invoice(other)
            if not part:
                raise UserError(_(
                    'ใบ %(so)s ลูกค้าชำระครบแล้วในระบบเดิม (%(refs)s) ไม่มียอดค้างให้ออกใบแจ้งหนี้'
                ) % {'so': order.name, 'refs': order.npd_o14_invoice_refs or '-'})
            order.npd_o14_reissued = True
            moves |= part
        return moves

    def _npd_create_o14_other_invoice(self, other):
        """ใบแจ้งหนี้ยอดค้างของใบประเภทอื่นฝั่ง 14 (ประเภท/สมุด/สินค้าเดิม ยอด = ยอดค้าง)"""
        self.ensure_one()
        vals = self._prepare_invoice()
        vals.pop('invoice_line_ids', None)
        vals['move_type'] = other.get('move_type') or 'out_invoice'
        Move = self.env['account.move']
        for name in ('reason_code_id', 'document_type', 'pfb_so_type', 'contact_type',
                     'closing_type', 'debt_payment_type', 'journal_id'):
            if other.get(name) and name in Move._fields:
                vals[name] = other[name]
        vals['ref'] = (_('เครดิตคงเหลือจาก %s (%s)') if vals['move_type'] == 'out_refund'
                       else _('ยอดค้างจาก %s (%s)')) % (other['o14_name'], other.get('type_name') or '-')
        vals['npd_o14_reissue_order_id'] = self.id
        taxes = self.env['account.tax'].browse(other.get('tax_ids') or [])
        rate = sum(t.amount for t in taxes if t.amount_type == 'percent' and not t.price_include) / 100.0
        line = {
            'name': _('%s — ยอดค้างจาก %s') % (other.get('line_name') or other.get('type_name') or '', other['o14_name']),
            'quantity': 1,
            'price_unit': round(other['residual'] / (1.0 + rate), 2),
            'tax_ids': [(6, 0, taxes.ids)],
        }
        if other.get('product_id'):
            line['product_id'] = other['product_id']
        vals['invoice_line_ids'] = [(0, 0, line)]
        move = Move.with_company(self.company_id).create(vals)
        # เศษปัด VAT: ขยับราคาทีละสตางค์จนยอดรวม = ยอดค้างพอดี
        inv_line = move.invoice_line_ids[:1]
        for _i in range(5):
            diff = round(move.amount_total - other['residual'], 2)
            if abs(diff) < 0.005:
                break
            inv_line.write({'price_unit': round(inv_line.price_unit + (0.01 if diff < 0 else -0.01), 2)})
        move.message_post(body=_('ใบแจ้งหนี้ยอดค้างจากระบบเดิม: %(o14)s (%(type)s) ยอดเต็ม %(total)s ค้าง %(left)s — จากใบ %(so)s') % {
            'o14': other['o14_name'], 'type': other.get('type_name') or '-',
            'total': '{:,.2f}'.format(other.get('total') or 0.0),
            'left': '{:,.2f}'.format(other['residual']), 'so': self.name})
        return move

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
        # เป้าคือยอดค้างของใบหลักตรง ๆ (ยอดใบฝั่ง 18 อาจต่างฝั่ง 14 เศษสตางค์)
        target_total = self.npd_o14_main_outstanding or (move.amount_total - self.npd_o14_paid_amount)
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


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    o14_line_id = fields.Integer(string='id บรรทัดฝั่ง 14', readonly=True, copy=False, index=True)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    npd_o14_deduct_order_id = fields.Many2one(
        'sale.order', string='หักยอดชำระเดิมของใบ', readonly=True, copy=False, index=True,
        ondelete='set null',
        help='บรรทัดหักยอดที่ลูกค้าชำระแล้วในระบบเดิม (ใบที่ยกมาจาก Odoo 14)')


class AccountMove(models.Model):
    _inherit = 'account.move'

    npd_o14_reissue_order_id = fields.Many2one(
        'sale.order', string='ออกยอดค้างจากใบ (ฝั่ง 14)', readonly=True, copy=False, index=True,
        ondelete='set null',
        help='ใบแจ้งหนี้ยอดค้างที่ออกจากใบเช่าที่ยกมาจาก Odoo 14')
