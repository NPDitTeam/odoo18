# -*- coding: utf-8 -*-
"""ยกใบเช่าต่ออายุจากฝั่ง Odoo 14

กฎที่ถือตลอดทั้งไฟล์นี้
* **ยอดต้องตรงต้นทางทุกบาท** สร้างเสร็จแล้วเทียบทันที ใบไหนไม่ตรงรายงานออกมา
  ไม่เขียนยอดทับให้ตรงเอง เพราะนั่นคือการซ่อนบั๊กไว้ในเอกสารที่ใช้คิดค่าคอม
* **กดซ้ำได้** ใบที่ยกมาแล้วจะถูกอัปเดตทับ ไม่สร้างซ้ำ
* **ไม่สร้างใบส่งของ** ตั้งสถานะตรง ๆ เพราะสต็อกยกมาจากยอดคงเหลือจริง
  ของฝั่ง 14 ซึ่งหักของที่ปล่อยเช่าออกไปแล้ว ถ้าปล่อยให้สร้างใบส่งของจะตัดซ้ำ
"""
import json
import logging

from odoo import fields, models, _
from odoo.exceptions import UserError

from .rental_importer import ORDER_FIELDS, LINE_FIELDS

_logger = logging.getLogger(__name__)


def _uom_field_name(env):
    """ชื่อช่องหน่วยนับบนบรรทัดใบเสนอราคา — Odoo เปลี่ยนชื่อระหว่างรุ่น"""
    fields_ = env['sale.order.line']._fields
    return 'product_uom_id' if 'product_uom_id' in fields_ else 'product_uom'

# ช่องที่ก็อปค่าลงใบฝั่ง 18 ได้ตรง ๆ ถ้าฝั่ง 18 มีช่องนั้น
COPY_AS_IS = [
    'npd_so_type', 'pfb_so_type', 'contact_type', 'delivery_type', 'on_site',
    'picking_policy',
    'renewal_bill_status', 'deposit_ref', 'rental_status',
    'start_rent_date', 'end_rent_date', 'pfb_date_of_rent',
    'rental_contract_no', 'rental_contract_prefix', 'is_in_rent',
    'total_rental_discount', 'deposit_return_status',
    'use_new_calc', 'use_baan_kheaw', 'vat_from_total',
    'client_order_ref',
    # วันที่จัดส่งสินค้า (คอลัมน์รายการดึงจากหัวใบ)
    'commitment_date',
]


class RentalOrderImport(models.Model):
    _inherit = 'npd.rental.import.config'

    # ------------------------------------------------------------------
    def _fetch_orders(self, date_from, date_to, limit=None, names=None):
        # ช่องประเภทใบที่ o14 ใช้จริงคือ pfb_so_type — npd_so_type เกือบทั้งหมดเป็น sale
        # (เดิมกรองด้วย npd_so_type: กรุงเทพ/เอส กรุ๊ปหาไม่เจอสักใบ อินเตอร์เจอ 77 จาก 5,286)
        domain = [('pfb_so_type', '=', 'rent')]
        if names:
            # ระบุเลขใบมาเอง (ปุ่ม 4) ไม่บังคับว่าต้องเป็นบิลต่ออายุ ผู้ใช้เลือกใบเองแล้ว
            domain.append(('name', 'in', list(names)))
        else:
            domain.append(('renewal_bill_status', '=', 'renew'))
            domain += [('date_order', '>=', '%s 00:00:00' % date_from),
                       ('date_order', '<=', '%s 23:59:59' % date_to)]
        available = set(self.execute_kw('sale.order', 'fields_get',
                                        [[], ['type']]).keys())
        fields_list = [f for f in ORDER_FIELDS if f in available]
        kwargs = {'order': 'date_order, id'}
        if limit:
            kwargs['limit'] = limit
        return self.execute_kw('sale.order', 'search_read',
                               [domain, fields_list], kwargs)

    def _fetch_lines(self, order_ids):
        available = set(self.execute_kw('sale.order.line', 'fields_get',
                                        [[], ['type']]).keys())
        fields_list = [f for f in LINE_FIELDS if f in available] + ['order_id']
        rows = self.search_read_all(
            'sale.order.line', [('order_id', 'in', list(order_ids))], fields_list)
        grouped = {}
        for row in rows:
            grouped.setdefault(row['order_id'][0], []).append(row)
        return grouped

    def _partner_vat_index(self, rows):
        """เลขผู้เสียภาษีของลูกค้าแต่ละใบ — ใช้จับคู่ลูกค้าให้แม่นกว่าชื่อ"""
        partner_ids = {row['partner_id'][0] for row in rows
                       if row.get('partner_id')}
        if not partner_ids:
            return {}
        vat_by_partner = {
            r['id']: (r.get('vat') or '').strip()
            for r in self.execute_kw('res.partner', 'read',
                                     [sorted(partner_ids), ['vat']])}
        return {row['id']: vat_by_partner.get(row['partner_id'][0], '')
                for row in rows if row.get('partner_id')}

    def _product_code_index(self, product_ids):
        """รหัสสินค้าฝั่ง 14 ต่อ id — ใช้จับคู่กับฝั่ง 18 ให้แม่นกว่าใช้ชื่อ"""
        if not product_ids:
            return {}
        rows = self.execute_kw(
            'product.product', 'read',
            [sorted(product_ids), ['default_code']])
        return {r['id']: (r.get('default_code') or '').strip() for r in rows}

    # ------------------------------------------------------------------
    def _prepare_order_values(self, row, partner, branch):
        Order = self.env['sale.order']
        values = {
            # ใช้เลขใบเดิมของ o14 (เลขย้อนหลัง อ้างอิงกับลูกค้า/เอกสารเดิม) ไม่ออกเลขใหม่
            'name': row.get('name'),
            'partner_id': partner.id,
            'date_order': row.get('date_order'),
            'company_id': self.company_id.id,
            'o14_imported': True,
            'o14_source_db': self.db_name,
            'o14_order_id': row['id'],
            'o14_order_name': row.get('name'),
        }
        if branch and 'branch_id' in Order._fields:
            values['branch_id'] = branch.id
        # พนักงานขาย / Sales ที่ติดต่อ (ไม่มีฝั่ง 18 → สร้างผู้ใช้แบบปิดใช้งานให้)
        for fname in ('user_id', 'sales_contact'):
            if fname in Order._fields and row.get(fname):
                user, _new = self._map_user(row[fname])
                if user:
                    values[fname] = user.id
        # ใบที่ยกมาเป็นใบสั่งขายแล้ว ไม่ใช่ใบเสนอราคา (sale_isolated_quotation แยกด้วย order_sequence)
        # ไม่ตั้ง ฟอร์มจะขึ้นหัวใบเสนอราคา + ปุ่ม Convert to Order
        if 'order_sequence' in Order._fields:
            values['order_sequence'] = True
        # ช่องบังคับกรอกของฝั่ง 18 ที่ต้องแปลงข้ามฐาน ไม่ใช่ก็อปค่าดิบ
        if 'customer_channel_id' in Order._fields:
            values['customer_channel_id'] = self._map_channel(
                row.get('customer_channel_id')).id
        pricelist = self._map_pricelist(row.get('pricelist_id'), branch)
        if pricelist:
            values['pricelist_id'] = pricelist.id
        # ที่อยู่ออกบิล/ส่งของ ใช้ของลูกค้าเองเสมอ เพราะ id ข้ามฐานไม่ตรงกัน
        values['partner_invoice_id'] = partner.id
        values['partner_shipping_id'] = partner.id
        for name in COPY_AS_IS:
            if name in Order._fields and name in row:
                value = row[name]
                if isinstance(value, (list, tuple)):
                    continue
                values[name] = value if value is not False else False
        if row.get('note') and 'note' in Order._fields:
            values['note'] = row['note']
        return values

    def _prepare_line_values(self, row, code_index, tax_names=None):
        product = self._map_product(row.get('product_id'), code_index)
        display_type = row.get('display_type')
        values = {
            'name': row.get('name') or '',
            'sequence': row.get('sequence') or 10,
        }
        if display_type:
            # บรรทัดหัวข้อ/หมายเหตุ ไม่มีสินค้าและไม่มียอด
            values['display_type'] = display_type
            return values, None
        if not product:
            return None, _('ไม่พบสินค้า %s') % (row.get('product_id') or '-')
        o14_label = (row.get('product_id') or [0, ''])[1]
        conflict = self._product_name_conflict(o14_label, product)
        if conflict:
            # รหัสเดียวกันแต่ฝั่ง 18 เป็นคนละสินค้า ยกไปจะได้สินค้า/ราคาผิด ต้องแก้รหัสก่อน
            return None, _('รหัสเดียวกันแต่เป็นคนละสินค้า: ฝั่ง 14 "%s" / ฝั่ง 18 "%s"') % (o14_label, conflict)
        uom = self._map_uom(row.get('product_uom')) or product.uom_id
        values.update({
            'product_id': product.id,
            'product_uom_qty': row.get('product_uom_qty') or 0.0,
            # ชื่อช่องหน่วยนับต่างกันตามรุ่น ฝั่งนี้ยังเป็น product_uom
            _uom_field_name(self.env): uom.id,
            'price_unit': row.get('price_unit') or 0.0,
            'discount': row.get('discount') or 0.0,
            'tax_id': [(6, 0, self._map_taxes(row.get('tax_id'), tax_names).ids)],
            'o14_line_id': row.get('id') or 0,
        })
        # ส่วนลดรายบรรทัด (ใช้เกณฑ์ขออนุมัติ 50%) — ฝั่ง 14 บางฐานไม่มีช่อง ก็ข้ามไป
        Line = self.env['sale.order.line']
        for name in ('discount_type_selection', 'discount_method', 'discount_amount'):
            if name in Line._fields and row.get(name):
                values[name] = row[name]
        # น้ำหนักต่อหน่วยตามฝั่ง 14 ถ้ามี ไม่มีก็ให้ดึงจากน้ำหนักสินค้าฝั่ง 18 เอง
        if 'second_uom_qty' in Line._fields and row.get('second_uom_qty'):
            values['second_uom_qty'] = row['second_uom_qty']
        return values, None

    def _set_o14_amounts(self, order, line_rows):
        """เก็บยอดใบตามฝั่ง 14 (ผลรวมรายการ) — หัวใบ/สรุปยอดจะใช้ยอดนี้ถ้าต่างแค่เศษปัด"""
        want = self._o14_line_amounts(line_rows)
        order.write({
            'npd_o14_amount_untaxed': want['amount_untaxed'],
            'npd_o14_amount_tax': want['amount_tax'],
            'npd_o14_amount_total': want['amount_total'],
        })
        order.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total', 'tax_totals'])

    def _set_rent_qty(self, order, line_rows):
        """จำนวนเช่า (pfb_quantity) ตามฝั่ง 14 — เขียนลงตารางตรง ๆ หลังยอดเงินลงตัวแล้ว

        เขียนผ่าน ORM แล้ว pfb_npd_all_customs จะคำนวณจำนวน (วัน × ชิ้น) ใหม่
        ซึ่งไปปลุกให้ราคาดึงจากรายการราคาใหม่ ราคา VAT ใน ถูกถอด VAT ซ้ำ ยอดใบผิด
        """
        if 'pfb_quantity' not in order.order_line._fields:
            return
        qty = {r['id']: int(r.get('pfb_quantity') or 0) for r in line_rows if r.get('pfb_quantity')}
        lines = order.order_line.filtered(lambda l: l.o14_line_id in qty)
        if not lines:
            return
        order.flush_recordset()
        lines.flush_recordset()
        # เขียนตรงแล้วน้ำหนักรวมไม่คำนวณตาม (sale_api_rent: จำนวน × น้ำหนักต่อหน่วย) — ใส่ไปพร้อมกัน
        weight = 'total_weight' in lines._fields and not getattr(order, 'is_renew_green_house', False)
        for line in lines:
            if weight:
                self.env.cr.execute(
                    'UPDATE sale_order_line SET pfb_quantity = %s, total_weight = %s * COALESCE(second_uom_qty, 0) '
                    'WHERE id = %s', (qty[line.o14_line_id], qty[line.o14_line_id], line.id))
            else:
                self.env.cr.execute('UPDATE sale_order_line SET pfb_quantity = %s WHERE id = %s',
                                    (qty[line.o14_line_id], line.id))
        lines.invalidate_recordset(['pfb_quantity', 'total_weight'] if weight else ['pfb_quantity'])

    # ------------------------------------------------------------------
    def _fetch_o14_net_delivered(self, order_ids):
        """ของที่ยังอยู่กับลูกค้าต่อบรรทัดใบเช่าฝั่ง 14 = ส่งออก - รับคืน (ใบส่ง/รับที่ทำเสร็จแล้ว)"""
        if not order_ids:
            return {}
        orders = self.execute_kw('sale.order', 'read', [list(order_ids), ['picking_ids']])
        picking_ids = sorted({p for r in orders for p in (r.get('picking_ids') or [])})
        if not picking_ids:
            return {}
        moves = self.execute_kw('stock.move', 'search_read', [[
            ('picking_id', 'in', picking_ids), ('state', '=', 'done'), ('sale_line_id', '!=', False)],
            ['sale_line_id', 'quantity_done', 'location_id', 'location_dest_id']])
        loc_ids = sorted({m['location_id'][0] for m in moves} | {m['location_dest_id'][0] for m in moves})
        usage = {l['id']: l['usage'] for l in self.execute_kw('stock.location', 'read', [loc_ids, ['usage']])} \
            if loc_ids else {}
        net = {}
        for m in moves:
            src, dst = usage.get(m['location_id'][0]), usage.get(m['location_dest_id'][0])
            qty = m.get('quantity_done') or 0.0
            sl = m['sale_line_id'][0]
            if dst == 'customer' and src != 'customer':
                net[sl] = net.get(sl, 0.0) + qty
            elif src == 'customer' and dst != 'customer':
                net[sl] = net.get(sl, 0.0) - qty
        return {k: v for k, v in net.items() if v > 0.0001}

    def _cut_stock_from_o14(self, order, net_by_o14_line):
        """ตัดสต็อกให้ตรงฝั่ง 14: สร้างใบส่งของ (เสร็จแล้ว) ของที่ยังอยู่กับลูกค้า ผูกกับบรรทัดใบเช่า

        ยอดคงเหลือฝั่ง 14 หักของที่อยู่กับลูกค้าไปแล้ว จึงเติมเข้าคลังก่อนแล้วค่อยส่งออก
        คงเหลือในคลังเท่าเดิม แต่ใบเช่าฝั่ง 18 มีใบส่งของ/จำนวนส่งแล้วเหมือนฝั่ง 14
        คืน (ชื่อใบส่งของ, จำนวนรายการ) หรือ None ถ้าไม่มีอะไรต้องตัด
        """
        lines = order.order_line.filtered(
            lambda l: l.o14_line_id in net_by_o14_line and l.product_id and l.product_id.type == 'consu')
        if not lines or order.picking_ids.filtered(lambda p: p.state == 'done'):
            return None
        env = self.env
        company = order.company_id
        warehouse = env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
        if not warehouse:
            raise UserError(_('บริษัท %s ยังไม่มีคลังสินค้าฝั่ง 18') % company.name)
        source = env['stock.location']
        if 'stock.cut.confirm.wizard' in env and order.branch_id:
            source = env['stock.cut.confirm.wizard'].sudo()._get_branch_internal_location(
                order.branch_id, lines.mapped('product_id').ids)
        source = source or warehouse.lot_stock_id
        dest = env.ref('stock.stock_location_customers')
        Quant = env['stock.quant'].sudo()
        move_vals = []
        for line in lines:
            qty = net_by_o14_line[line.o14_line_id]
            # เติมคืนก่อน (ฝั่ง 14 หักของที่อยู่กับลูกค้าออกจากคงเหลือแล้ว) กันตัดซ้ำ
            Quant._update_available_quantity(line.product_id, source, qty)
            move_vals.append((0, 0, {
                'name': line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': qty,
                'product_uom': line.product_id.uom_id.id,
                'location_id': source.id,
                'location_dest_id': dest.id,
                'sale_line_id': line.id,
                'company_id': company.id,
            }))
        picking_vals = {
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': source.id,
            'location_dest_id': dest.id,
            'partner_id': order.partner_shipping_id.id,
            'origin': order.name,
            'sale_id': order.id,
            'company_id': company.id,
            'move_ids': move_vals,
        }
        Picking = env['stock.picking'].sudo().with_company(company)
        if 'branch_id' in Picking._fields and order.branch_id:
            picking_vals['branch_id'] = order.branch_id.id
        picking = Picking.create(picking_vals)
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move._set_quantity_done(move.product_uom_qty)
            move.picked = True
        picking.with_context(skip_backorder=True, cancel_backorder=True, skip_sms=True,
                             skip_immediate=True).button_validate()
        if picking.state != 'done':
            raise UserError(_('ตัดสต็อกไม่สำเร็จ (ใบส่งของ %s สถานะ %s)') % (picking.name, picking.state))
        picking.message_post(body=_('ตัดสต็อกตามฝั่ง 14 ตอนยกใบเช่า (ของที่ยังอยู่กับลูกค้า)'))
        return picking.name, len(lines)

    # ------------------------------------------------------------------
    def action_import_orders(self, date_from=None, date_to=None,
                             limit=None, names=None):
        """ยกใบเช่าต่ออายุตามช่วงวันที่สั่งซื้อ (หรือระบุเลขใบมาตรง ๆ)"""
        self.ensure_one()
        if not names and not (date_from and date_to):
            raise UserError(_('ต้องระบุช่วงวันที่ หรือเลขใบที่ต้องการยก'))

        rows = self._fetch_orders(date_from, date_to, limit=limit, names=names)
        if not rows:
            text = _('ไม่พบใบเช่าต่ออายุที่ตรงเงื่อนไขในฝั่ง %s') % self.db_name
            self._note(text)
            return text

        lines_by_order = self._fetch_lines([r['id'] for r in rows])
        product_ids = {line['product_id'][0]
                       for lines in lines_by_order.values() for line in lines
                       if line.get('product_id')}
        code_index = self._product_code_index(product_ids)
        partner_vat = self._partner_vat_index(rows)
        # search_read ของ many2many ส่งมาแค่ id ต้องขอชื่อภาษีมาเอง ไม่งั้นจับคู่ภาษีมั่ว
        tax_names = self._tax_name_index({
            t for lines in lines_by_order.values() for line in lines
            for t in (line.get('tax_id') or []) if isinstance(t, int)})

        Order = self.env['sale.order'].sudo().with_context(
            allowed_company_ids=self._all_companies())
        created, updated, blocked, failed, mismatched = [], [], [], [], []
        # ใบแจ้งหนี้/การชำระฝั่ง 14 → ใบแจ้งหนี้จากใบนี้ฝั่ง 18 ต้องเป็นแค่ยอดค้าง
        invoice_status = self._fetch_o14_invoice_status(rows)
        partly_paid = []
        delivered = self._fetch_o14_net_delivered([r['id'] for r in rows])
        stock_cut = []

        # สินค้าที่ใบใช้แต่ฝั่ง 18 ยังไม่มี: คัดลอกจาก o14 พร้อมลงสต็อกตาม o14
        new_products, product_failed = self._ensure_products_from_o14(
            sorted(product_ids), code_index)
        new_partners, price_updates = [], 0

        for row in rows:
            name = row.get('name')
            # โมดูลปัดยอดรวมตามขั้นยังไม่ได้พอร์ต ยกมาแล้วยอดจะไม่ตรง
            # กันไว้ดีกว่าปล่อยใบที่ยอดผิดเข้าไปปนกับใบที่ถูก
            if row.get('x_round_enabled'):
                blocked.append(_('%s ตั้งปัดยอดรวมเอง (x_round) ยังพอร์ตไม่ได้')
                               % name)
                continue
            partner = self._map_partner(
                row.get('partner_id'), vat=partner_vat.get(row['id']))
            if not partner:
                # ฝั่ง 18 ไม่มีจริง (ไม่เจอทั้งเลขผู้เสียภาษีและชื่อ) คัดลอกจาก o14
                try:
                    with self.env.cr.savepoint():
                        partner = self._ensure_partner_from_o14(row.get('partner_id'))
                        new_partners.append('%s (%s)' % (partner.name, partner.vat or '-'))
                except Exception as error:
                    partner = self.env['res.partner'].browse()
                    blocked.append(_('%s สร้างลูกค้า "%s" ไม่ได้: %s')
                                   % (name, (row.get('partner_id') or ['', '-'])[1], str(error)[:150]))
                    continue
            branch = self._map_branch(row.get('branch_id'))
            clash = self._name_clash(row)
            if clash:
                blocked.append(_('%s เลขซ้ำกับใบ %s ที่มีอยู่แล้วในบริษัทเดียวกันฝั่ง 18')
                               % (name, clash.display_name))
                continue

            try:
                with self.env.cr.savepoint():
                    existing = Order.search([('o14_order_name', '=', name),
                                             ('o14_source_db', '=', self.db_name)],
                                            limit=1)
                    if existing and existing.picking_ids.filtered(lambda p: p.state == 'done'):
                        blocked.append(_('%s ตัดสต็อกไปแล้ว (%s) ไม่ยกทับ') % (
                            name, ', '.join(existing.picking_ids.filtered(lambda p: p.state == 'done').mapped('name'))))
                        continue
                    if existing and existing._npd_o14_active_reissue():
                        blocked.append(_('%s ออกใบแจ้งหนี้ยอดค้างไปแล้ว (%s) ไม่ยกทับ — ถ้าต้องยกใหม่ให้ยกเลิกใบแจ้งหนี้ก่อน')
                                       % (name, ', '.join(existing._npd_o14_active_reissue().mapped(
                                           lambda m: m.name if m.name and m.name != '/' else _('ร่าง')))))
                        continue
                    values = self._prepare_order_values(row, partner, branch)
                    # ราคาในรายการราคาของสาขาต้องตรง o14 ด้วย (ใบหลังย้ายจะดึงราคาจากตรงนี้)
                    pricelist = self.env['product.pricelist'].browse(values.get('pricelist_id'))
                    if pricelist and self._pricelist_matches(row, pricelist):
                        o14_pids = {l['product_id'][0] for l in lines_by_order.get(row['id'], [])
                                    if l.get('product_id')}
                        price_updates += self._sync_pricelist_prices(
                            pricelist, self._o14_pricelist_prices(row.get('pricelist_id'), o14_pids),
                            code_index)
                    line_commands, problem = [], None
                    for line_row in sorted(lines_by_order.get(row['id'], []),
                                           key=lambda r: r.get('sequence') or 0):
                        line_values, problem = self._prepare_line_values(
                            line_row, code_index, tax_names)
                        if problem:
                            break
                        line_commands.append((0, 0, line_values))
                    if problem:
                        blocked.append('%s %s' % (name, problem))
                        continue
                    if existing:
                        # ใบที่ยืนยันแล้วลบบรรทัดไม่ได้ ต้องคืนเป็นร่างก่อน
                        # เขียนสถานะตรง ๆ ไม่เรียก action_cancel/action_draft
                        # เพราะสองตัวนั้นจะไปยุ่งกับใบส่งของและใบแจ้งหนี้
                        if existing.state != 'draft':
                            existing.write({'state': 'draft'})
                        existing.order_line.unlink()
                        existing.write(dict(values, order_line=line_commands))
                        order = existing
                        updated.append(name)
                    else:
                        order = Order.create(dict(values, order_line=line_commands))
                        created.append(name)
                    # ตั้งสถานะตรง ๆ ไม่เรียก action_confirm เพื่อไม่ให้เกิด
                    # ใบส่งของซ้ำกับสต็อกที่ยกมาแล้ว
                    if row.get('state') and order.state != row['state']:
                        order.write({'state': row['state']})
                    # o14 เก็บราคารวม VAT ปัด 2 ตำแหน่ง (1.28) → แปลงเป็น 1.2840 ให้ยอดตรง o14
                    order.order_line._npd_normalize_vat_price()
                    order.order_line.with_context(
                        npd_skip_round=True)._npd_recalc_amounts()
                    order.invalidate_recordset(
                        ['amount_untaxed', 'amount_tax', 'amount_total'])
                    self._set_rent_qty(order, lines_by_order.get(row['id'], []))
                    self._set_o14_amounts(order, lines_by_order.get(row['id'], []))
                    diff = self._compare_amounts(order, row, lines_by_order.get(row['id'], []))
                    if diff:
                        mismatched.append('%s %s' % (name, diff))
                    # ตัดสต็อกตามฝั่ง 14 (ของที่ยังอยู่กับลูกค้า) ก่อนออกใบแจ้งหนี้
                    if order.state == 'sale':
                        cut = self._cut_stock_from_o14(order, delivered)
                        if cut:
                            stock_cut.append(_('%s → ตัดสต็อก %s (%s รายการ)') % (name, cut[0], cut[1]))
                    inv = invoice_status.get(row['id'])
                    if inv:
                        order.write(inv)
                        # มียอดค้าง (บางส่วน) → สร้างใบแจ้งหนี้ยอดค้างแยกตามประเภทให้เลย (ฉบับร่าง)
                        has_due = inv['npd_o14_main_outstanding'] > 0.005 or inv.get('npd_o14_open_others')
                        if has_due and order.state == 'sale':
                            moves = order._create_invoices()
                            partly_paid.append(_('%s → สร้างใบแจ้งหนี้ (ร่าง) %s ใบ: %s') % (
                                name, len(moves), ' | '.join('%s %s' % (
                                    (m.reason_code_id.name if 'reason_code_id' in m._fields and m.reason_code_id
                                     else _('ใบแจ้งหนี้')) + (_(' (ลดหนี้)') if m.move_type == 'out_refund' else ''),
                                    '{:,.2f}'.format(m.amount_total)) for m in moves)))
                        elif has_due:
                            partly_paid.append(_('%s ยอดค้าง %s แต่ใบยังไม่ยืนยัน (สถานะ %s) ไม่ได้สร้างใบแจ้งหนี้') % (
                                name, '{:,.2f}'.format(inv['npd_o14_outstanding']), order.state))
            except Exception as error:
                _logger.exception('[RENTAL IMPORT] %s ล้มเหลว', name)
                failed.append('%s: %s' % (name, str(error)[:200]))

        self.env.cr.commit()
        text = self._import_report(rows, created, updated, blocked,
                                   failed, mismatched)
        if stock_cut:
            text += '\n\n' + _('ตัดสต็อกตามฝั่ง 14 (ของที่ยังอยู่กับลูกค้า) %s ใบ:') % len(stock_cut) \
                + '\n  ' + '\n  '.join(stock_cut[:50])
        if partly_paid:
            text += '\n\n' + _('ใบที่มียอดค้างจากระบบเดิม — สร้างใบแจ้งหนี้ยอดค้างแยกตามประเภทให้แล้ว (%s ใบ):') \
                % len(partly_paid) + '\n  ' + '\n  '.join(partly_paid[:50])
        if new_partners:
            text += '\n\n' + _('สร้างลูกค้าใหม่จาก o14 (%s ราย):') % len(new_partners) \
                + '\n  ' + '\n  '.join(new_partners[:50])
        if price_updates:
            text += '\n\n' + _('ปรับราคาในรายการราคาให้ตรง o14: %s รายการ') % price_updates
        if new_products:
            text += '\n\n' + _('สร้างสินค้าใหม่จาก o14 (%s ตัว):') % len(new_products) \
                + '\n  ' + '\n  '.join(new_products[:50])
        if product_failed:
            text += '\n\n' + _('สร้างสินค้าไม่ได้:') + '\n  ' + '\n  '.join(product_failed[:20])
        self._note(text)
        return text

    def _fetch_o14_invoice_status(self, rows):
        """ใบแจ้งหนี้ของแต่ละใบฝั่ง 14 → ยอดออกใบ / ชำระแล้ว / ค้าง

        ยอดค้าง = (ยอดใบ - ยอดออกใบแจ้งหนี้) + ยอดค้างสุทธิของใบแจ้งหนี้ (ใบลดหนี้หักออก)
        ชำระแล้ว (ส่วนที่จะหักตอนออกใบแจ้งหนี้ฝั่ง 18) = ยอดใบ - ยอดค้าง
        นับเฉพาะใบที่ลงรายการแล้ว
        """
        result = {}
        ids = [r['id'] for r in rows]
        if not ids:
            return result
        so_rows = self.execute_kw('sale.order', 'read', [ids, ['invoice_ids', 'name']])
        so_inv = {r['id']: list(r.get('invoice_ids') or []) for r in so_rows}
        # ใบที่ผูกกับบรรทัดใบเช่า = ส่วนที่ออกใบแจ้งหนี้จากใบเช่าแล้ว
        linked = {oid: set(v) for oid, v in so_inv.items()}
        # ใบเพิ่มหนี้ (เช่น ค่าเช่าส่วนต่าง) สร้างจากใบแจ้งหนี้ ไม่ได้ผูกบรรทัดใบเช่า แต่ยอดค้างเป็นของใบนี้
        Move = 'account.move'
        mfields = set(self.execute_kw(Move, 'fields_get', [[], ['type']]).keys())
        for r in so_rows:
            extra = set()
            # ค้นเฉพาะใบเพิ่มหนี้ที่สร้างจากใบแจ้งหนี้ของใบนี้ ไม่ค้นจาก "เอกสารต้นทาง"
            # เพราะใบรับเงินประกัน (INS-) ก็ใส่เลขใบเช่าไว้ แต่เป็นเงินประกัน ไม่ใช่ค่าเช่า
            if 'debit_origin_id' in mfields and so_inv[r['id']]:
                extra |= set(self.execute_kw(Move, 'search', [[
                    ('debit_origin_id', 'in', so_inv[r['id']]), ('state', '=', 'posted'),
                    ('move_type', '=', 'out_invoice')]]))
            so_inv[r['id']] = sorted(set(so_inv[r['id']]) | extra)
        inv_ids = sorted({i for v in so_inv.values() for i in v})
        head_fields = [f for f in ('name', 'move_type', 'state', 'amount_total', 'amount_residual',
                                   'reason_code_id', 'document_type', 'pfb_so_type', 'contact_type',
                                   'closing_type', 'debt_payment_type', 'journal_id', 'ref')
                       if f in mfields]
        moves = {m['id']: m for m in self.execute_kw('account.move', 'read', [inv_ids, head_fields])} \
            if inv_ids else {}
        totals = {r['id']: r.get('amount_total') or 0.0 for r in rows}
        for oid in ids:
            inv_total = main_residual = 0.0
            refs, open_others = [], []
            for mid in so_inv.get(oid, []):
                m = moves.get(mid)
                if not m or m['state'] != 'posted':
                    continue
                sign = 1 if m['move_type'] == 'out_invoice' else -1 if m['move_type'] == 'out_refund' else 0
                if not sign:
                    continue
                refs.append(m['name'])
                if sign < 0:
                    # ใบลดหนี้ที่ยังไม่ได้ใช้ (ลูกค้ามีเครดิตค้าง) → ออกใบลดหนี้ฝั่ง 18 แยกใบ
                    if (m['amount_residual'] or 0.0) > 0.005:
                        open_others.append(m)
                elif mid in linked.get(oid, ()):
                    # ใบหลักที่ออกจากบรรทัดใบเช่า
                    inv_total += m['amount_total'] or 0.0
                    main_residual += m['amount_residual'] or 0.0
                elif (m['amount_residual'] or 0.0) > 0.005:
                    # ใบประเภทอื่นที่ค้าง (เช่น ค่าเช่าส่วนต่าง สินค้าหาย/ชำรุด) ออกแยกใบตามประเภทเดิม
                    open_others.append(m)
            so_total = totals.get(oid, 0.0)
            uninvoiced = so_total - inv_total
            if refs and uninvoiced < 1.0:
                uninvoiced = 0.0  # ยอดใบกับใบแจ้งหนี้ต่างกันแค่เศษปัด VAT ไม่ใช่ส่วนที่ยังไม่ออกใบ
            main_outstanding = round(max(uninvoiced, 0.0) + main_residual, 2)
            if main_outstanding < 1.0:
                main_outstanding = 0.0  # ค้างไม่ถึงบาท = เศษปัด ไม่ออกใบแจ้งหนี้
            others = self._o14_open_invoice_payload(open_others)
            result[oid] = {
                'npd_o14_invoice_refs': ', '.join(refs) or False,
                'npd_o14_invoiced_total': round(inv_total, 2),
                'npd_o14_main_outstanding': main_outstanding,
                'npd_o14_paid_amount': round(max(so_total - main_outstanding, 0.0), 2) if refs else 0.0,
                'npd_o14_outstanding': round(main_outstanding + sum(
                    o['residual'] * (-1 if o['move_type'] == 'out_refund' else 1) for o in others), 2),
                'npd_o14_open_others': json.dumps(others, ensure_ascii=False) if others else False,
            }
        return result

    def _o14_open_invoice_payload(self, moves):
        """ใบที่ค้างนอกจากใบหลัก → ข้อมูลพอสำหรับออกใบแจ้งหนี้ฝั่ง 18 แยกตามประเภทเดิม"""
        if not moves:
            return []
        lines = self.execute_kw('account.move.line', 'search_read', [[
            ('move_id', 'in', [m['id'] for m in moves]), ('exclude_from_invoice_tab', '=', False),
            ('display_type', '=', False)], ['move_id', 'product_id', 'name', 'tax_ids']])
        tax_names = self._tax_name_index({t for l in lines for t in (l.get('tax_ids') or [])})
        Journal = self.env['account.journal'].sudo().with_context(lang='th_TH')
        Reason = self.env['scrap.reason.code'].sudo() if 'scrap.reason.code' in self.env else None
        payload = []
        for m in moves:
            mine = [l for l in lines if l['move_id'][0] == m['id']]
            first = mine[0] if mine else {}
            product = self._map_product(first.get('product_id')) if first.get('product_id') else None
            taxes = self._map_taxes(first.get('tax_ids') or [], tax_names)
            journal = Journal.browse()
            if m.get('journal_id'):
                jname = m['journal_id'][1]
                journal = Journal.search([('company_id', '=', self.company_id.id), ('type', '=', 'sale')]) \
                    .filtered(lambda j: ' '.join((j.name or '').split()) == ' '.join(jname.split()))[:1]
            reason = None
            if Reason is not None and m.get('reason_code_id'):
                reason = Reason.search([('name', '=', m['reason_code_id'][1])], limit=1)
            payload.append({
                'o14_name': m['name'],
                'move_type': m['move_type'],
                'residual': round(m['amount_residual'] or 0.0, 2),
                'total': round(m['amount_total'] or 0.0, 2),
                'type_name': m['reason_code_id'][1] if m.get('reason_code_id') else '',
                'reason_code_id': reason.id if reason else False,
                'document_type': m.get('document_type') or False,
                'pfb_so_type': m.get('pfb_so_type') or False,
                'contact_type': m.get('contact_type') or False,
                'closing_type': m.get('closing_type') or False,
                'debt_payment_type': m.get('debt_payment_type') or False,
                'journal_id': journal.id or False,
                'product_id': product.id if product else False,
                'line_name': first.get('name') or m.get('ref') or m['name'],
                'tax_ids': taxes.ids,
            })
        return payload

    def _name_clash(self, row):
        """ใบฝั่ง 18 ที่ใช้เลขเดียวกันในบริษัทเดียวกัน และไม่ใช่ใบที่ยกมาจากใบนี้เอง"""
        return self.env['sale.order'].sudo().with_context(
            allowed_company_ids=self._all_companies()).search([
                ('name', '=', row.get('name')),
                ('company_id', '=', self.company_id.id),
                '|', ('o14_order_name', '!=', row.get('name')),
                ('o14_source_db', '!=', self.db_name),
            ], limit=1)

    def _pricelist_matches(self, row, pricelist):
        """รายการราคาฝั่ง 18 ที่ได้ ตรงชื่อกับของ o14 จริง (ไม่ใช่ตัวสำรอง "เริ่มต้น")"""
        o14 = ((row.get('pricelist_id') or [0, ''])[1] or '').strip()
        if o14.endswith(')') and '(' in o14:
            o14 = o14[:o14.rfind('(')].strip()
        return bool(o14) and pricelist.with_context(lang='th_TH').name.strip().startswith(o14)

    def _o14_line_amounts(self, o14_lines):
        lines = [l for l in o14_lines if not l.get('display_type')]
        untaxed = round(sum(l.get('price_subtotal') or 0.0 for l in lines), 2)
        total = round(sum(l.get('price_total') or 0.0 for l in lines), 2)
        return {'amount_untaxed': untaxed, 'amount_tax': round(total - untaxed, 2), 'amount_total': total}

    def _compare_amounts(self, order, row, o14_lines=None):
        """คืนข้อความบอกส่วนต่าง ถ้ายอดตรงหมดคืนค่าว่าง

        เทียบกับยอดหัวใบ o14 ก่อน ถ้าไม่ตรงแต่ตรงกับยอดรวมของรายการ o14 ถือว่าตรง
        (หัวใบ o14 ค้างได้ เช่นเปลี่ยนวันเช่าแล้วหัวใบไม่คำนวณใหม่)
        """
        if o14_lines:
            want = self._o14_line_amounts(o14_lines)
            if all(abs(round(order[f] or 0.0, 2) - want[f]) < 0.01 for f in want):
                return ''
        parts = []
        for field_name, label in (('amount_untaxed', 'ก่อนภาษี'),
                                  ('amount_tax', 'ภาษี'),
                                  ('amount_total', 'รวม')):
            got = round(order[field_name] or 0.0, 2)
            want = round(row.get(field_name) or 0.0, 2)
            if abs(got - want) >= 0.01:
                parts.append('%s 14=%.2f 18=%.2f' % (label, want, got))
        return ' | '.join(parts)

    def _import_report(self, rows, created, updated, blocked, failed, mismatched):
        lines = [_('ยกใบเช่าจาก %s — เจอ %s ใบ | สร้าง %s | อัปเดต %s | '
                   'กันไว้ %s | ล้มเหลว %s | ยอดไม่ตรง %s')
                 % (self.db_name, len(rows), len(created), len(updated),
                    len(blocked), len(failed), len(mismatched))]
        for label, items in ((_('ยอดไม่ตรงต้นทาง'), mismatched),
                             (_('กันไว้ไม่ยกมา'), blocked),
                             (_('ล้มเหลว'), failed)):
            if items:
                lines.append('')
                lines.append('%s:' % label)
                lines.extend('  %s' % item for item in items[:30])
        return '\n'.join(lines)
