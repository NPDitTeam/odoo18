# -*- coding: utf-8 -*-
"""ยกใบเช่าต่ออายุจากฝั่ง Odoo 14

กฎที่ถือตลอดทั้งไฟล์นี้
* **ยอดต้องตรงต้นทางทุกบาท** สร้างเสร็จแล้วเทียบทันที ใบไหนไม่ตรงรายงานออกมา
  ไม่เขียนยอดทับให้ตรงเอง เพราะนั่นคือการซ่อนบั๊กไว้ในเอกสารที่ใช้คิดค่าคอม
* **กดซ้ำได้** ใบที่ยกมาแล้วจะถูกอัปเดตทับ ไม่สร้างซ้ำ
* **ไม่สร้างใบส่งของ** ตั้งสถานะตรง ๆ เพราะสต็อกยกมาจากยอดคงเหลือจริง
  ของฝั่ง 14 ซึ่งหักของที่ปล่อยเช่าออกไปแล้ว ถ้าปล่อยให้สร้างใบส่งของจะตัดซ้ำ
"""
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
        })
        return values, None

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
                    diff = self._compare_amounts(order, row, lines_by_order.get(row['id'], []))
                    if diff:
                        mismatched.append('%s %s' % (name, diff))
                    inv = invoice_status.get(row['id'])
                    if inv:
                        order.write(inv)
                        if inv['npd_o14_paid_amount'] > 0.005:
                            partly_paid.append(_('%s ชำระแล้ว %s ค้าง %s (%s)') % (
                                name, '{:,.2f}'.format(inv['npd_o14_paid_amount']),
                                '{:,.2f}'.format(inv['npd_o14_outstanding']), inv['npd_o14_invoice_refs']))
            except Exception as error:
                _logger.exception('[RENTAL IMPORT] %s ล้มเหลว', name)
                failed.append('%s: %s' % (name, str(error)[:200]))

        self.env.cr.commit()
        text = self._import_report(rows, created, updated, blocked,
                                   failed, mismatched)
        if partly_paid:
            text += '\n\n' + _('ใบที่ชำระแล้วในระบบเดิม — ใบแจ้งหนี้จากใบเหล่านี้จะหักยอดชำระเดิมให้เหลือยอดค้าง (%s ใบ):') \
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
        so_inv = {r['id']: r.get('invoice_ids') or [] for r in self.execute_kw(
            'sale.order', 'read', [ids, ['invoice_ids']])}
        inv_ids = sorted({i for v in so_inv.values() for i in v})
        moves = {m['id']: m for m in self.execute_kw('account.move', 'read', [inv_ids, [
            'name', 'move_type', 'state', 'amount_total', 'amount_residual']])} if inv_ids else {}
        totals = {r['id']: r.get('amount_total') or 0.0 for r in rows}
        for oid in ids:
            inv_total = residual = 0.0
            refs = []
            for mid in so_inv.get(oid, []):
                m = moves.get(mid)
                if not m or m['state'] != 'posted':
                    continue
                sign = 1 if m['move_type'] == 'out_invoice' else -1 if m['move_type'] == 'out_refund' else 0
                if not sign:
                    continue
                if sign > 0:
                    inv_total += m['amount_total'] or 0.0
                residual += sign * (m['amount_residual'] or 0.0)
                refs.append(m['name'])
            so_total = totals.get(oid, 0.0)
            uninvoiced = so_total - inv_total
            if refs and uninvoiced < 1.0:
                uninvoiced = 0.0  # ยอดใบกับใบแจ้งหนี้ต่างกันแค่เศษปัด VAT ไม่ใช่ส่วนที่ยังไม่ออกใบ
            outstanding = round(max(uninvoiced, 0.0) + residual, 2)
            result[oid] = {
                'npd_o14_invoice_refs': ', '.join(refs) or False,
                'npd_o14_invoiced_total': round(inv_total, 2),
                'npd_o14_paid_amount': round(max(so_total - outstanding, 0.0), 2) if refs else 0.0,
                'npd_o14_outstanding': outstanding,
            }
        return result

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
