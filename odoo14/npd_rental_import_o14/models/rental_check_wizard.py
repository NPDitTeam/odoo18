# -*- coding: utf-8 -*-
"""ตรวจ/ยกใบเช่ารายใบตามเลขเอกสาร o14

ใช้ก่อนยกจริง: กรอกเลขใบแล้วกด "ตรวจ" ระบบจะไล่ให้ดูว่าใบนั้นติดอะไร
(ไม่ใช่ใบเช่าต่ออายุ, หาลูกค้าไม่เจอ, สินค้าไม่มีฝั่ง 18, ภาษีจับคู่ไม่ได้, ยอดไม่ตรง)
โดยไม่บันทึกอะไรลงฐาน — ใบทดลองสร้างใน savepoint แล้วย้อนทิ้งทุกครั้ง
และตั้งชื่อใบเอง จึงไม่กินเลขลำดับใบเสนอราคาจริง
"""
import re

from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .rental_importer import ORDER_FIELDS, LINE_FIELDS


class _Rollback(Exception):
    """ใช้ย้อน savepoint ของใบทดลอง"""


OK = Markup('<span style="color:#198754">&#10004;</span>')
BAD = Markup('<span style="color:#dc3545">&#10008;</span>')
WARN = Markup('<span style="color:#b8860b">&#9888;</span>')


class RentalImportCheckWizard(models.TransientModel):
    _name = 'npd.rental.import.check.wizard'
    _description = 'ตรวจ/ยกใบเช่ารายใบจาก Odoo 14'

    config_id = fields.Many2one('npd.rental.import.config', string='การเชื่อมต่อ',
                                required=True, readonly=True)
    names = fields.Text(string='เลขเอกสาร (ฝั่ง 14)',
                        help='กรอกได้หลายใบ คั่นด้วยเว้นวรรค จุลภาค หรือขึ้นบรรทัดใหม่')
    result = fields.Html(string='ผล', readonly=True, sanitize=False)

    # ------------------------------------------------------------------
    def _parse_names(self):
        names = [n.strip() for n in re.split(r'[\s,;]+', self.names or '') if n.strip()]
        if not names:
            raise UserError(_('กรุณากรอกเลขเอกสารอย่างน้อย 1 ใบ'))
        if len(names) > 50:
            raise UserError(_('ตรวจได้ครั้งละไม่เกิน 50 ใบ'))
        return list(dict.fromkeys(names))

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'new', 'name': _('ตรวจ/ดึงรายใบ'),
        }

    # ------------------------------------------------------------------
    def action_check(self):
        """ตรวจอย่างเดียว ไม่บันทึก"""
        self.ensure_one()
        cfg = self.config_id
        names = self._parse_names()
        # อ่านตามเลขใบอย่างเดียว ไม่กรองประเภท จะได้บอกได้ว่าใบไหนไม่ใช่ใบเช่าต่ออายุ
        available = set(cfg.execute_kw('sale.order', 'fields_get', [[], ['type']]).keys())
        rows = cfg.execute_kw('sale.order', 'search_read',
                              [[('name', 'in', names)], [f for f in ORDER_FIELDS if f in available]])
        by_name = {r['name']: r for r in rows}
        lines_by_order = cfg._fetch_lines([r['id'] for r in rows]) if rows else {}
        product_ids = {l['product_id'][0] for ls in lines_by_order.values() for l in ls if l.get('product_id')}
        code_index = cfg._product_code_index(product_ids)
        tax_ids = {t for ls in lines_by_order.values() for l in ls for t in (l.get('tax_id') or [])
                   if isinstance(t, int)}
        tax_names = cfg._tax_name_index(tax_ids)
        partner_vat = cfg._partner_vat_index(rows) if rows else {}

        parts = []
        summary = {'ok': 0, 'bad': 0}
        for name in names:
            row = by_name.get(name)
            if not row:
                parts.append(self._block(name, [(BAD, _('ไม่พบเลขนี้ในฐาน %s') % cfg.db_name)], []))
                summary['bad'] += 1
                continue
            head, line_items, ready = self._check_one(row, lines_by_order.get(row['id'], []),
                                                      code_index, tax_names, partner_vat)
            parts.append(self._block(name, head, line_items))
            summary['ok' if ready else 'bad'] += 1
        title = Markup('<p><b>%s</b></p>') % (
            _('ตรวจ %(n)s ใบ — พร้อมยก %(ok)s ใบ | ติดปัญหา %(bad)s ใบ (ไม่ได้บันทึกอะไร)')
            % {'n': len(names), 'ok': summary['ok'], 'bad': summary['bad']})
        self.result = title + Markup('').join(parts)
        return self._reopen()

    def action_import(self):
        """ยกจริงเฉพาะใบที่กรอก (ใบที่ติดปัญหาจะถูกกันไว้ตามกฎเดิมของตัวยก)"""
        self.ensure_one()
        text = self.config_id.action_import_orders(names=self._parse_names())
        self.result = Markup('<pre style="white-space:pre-wrap">%s</pre>') % (text or '')
        return self._reopen()

    # ------------------------------------------------------------------
    def _block(self, name, head, line_items):
        html = Markup('<div style="border:1px solid #dee2e6;border-radius:6px;padding:8px 12px;margin:8px 0">'
                      '<b>%s</b><ul style="margin:6px 0">') % name
        for icon, text in head:
            html += Markup('<li>%s %s</li>') % (icon, text)
        html += Markup('</ul>')
        if line_items:
            html += Markup('<table class="table table-sm" style="font-size:12px;margin:0">'
                           '<thead><tr><th></th><th>สินค้า ฝั่ง 14</th><th>ฝั่ง 18</th><th>จำนวน</th>'
                           '<th>ราคาในใบ</th><th>รายการราคา 14 → 18</th><th>ภาษี ฝั่ง 14 → 18</th></tr></thead><tbody>')
            for icon, cols in line_items:
                html += Markup('<tr><td>%s</td>%s</tr>') % (
                    icon, Markup('').join(Markup('<td>%s</td>') % c for c in cols))
            html += Markup('</tbody></table>')
        return html + Markup('</div>')

    def _check_one(self, row, line_rows, code_index, tax_names, partner_vat):
        cfg = self.config_id
        head, items = [], []
        ready = True
        if row.get('pfb_so_type') != 'rent':
            head.append((BAD, _('ไม่ใช่ใบเช่า (ประเภท %s) ตัวยกจะข้าม') % (row.get('pfb_so_type') or '-')))
            ready = False
        if row.get('renewal_bill_status') != 'renew':
            head.append((BAD, _('ไม่ใช่ใบต่ออายุบิล (ไม่มีเลขอ้างอิงเงินประกัน) ตัวยกจะข้าม')))
            ready = False
        if row.get('x_round_enabled'):
            head.append((BAD, _('ตั้งปัดยอดรวมเอง (x_round) ยังพอร์ตไม่ได้ ตัวยกจะกันไว้')))
            ready = False
        head.append((OK, _('สถานะฝั่ง 14: %s | วันที่สั่ง %s | ยอดรวม %.2f') % (
            row.get('state'), (row.get('date_order') or '')[:10], row.get('amount_total') or 0.0)))
        lines_amt = cfg._o14_line_amounts(line_rows)
        if abs((row.get('amount_untaxed') or 0.0) - lines_amt['amount_untaxed']) >= 0.01 or \
                abs((row.get('amount_total') or 0.0) - lines_amt['amount_total']) >= 0.01:
            head.append((WARN, _('หัวใบ o14 ไม่ตรงผลรวมรายการ (หัวใบ ก่อนภาษี %.2f / รวม %.2f — รายการ %.2f / %.2f) '
                                 'จะยึดยอดของรายการ') % (row.get('amount_untaxed') or 0.0, row.get('amount_total') or 0.0,
                                                         lines_amt['amount_untaxed'], lines_amt['amount_total'])))

        partner = cfg._map_partner(row.get('partner_id'), vat=partner_vat.get(row['id']))
        o14_partner = (row.get('partner_id') or [0, '-'])[1]
        if partner:
            head.append((OK, _('ลูกค้า: %s → %s') % (o14_partner, partner.display_name)))
        else:
            head.append((WARN, _('ลูกค้า "%s" ยังไม่มีฝั่ง 18 (เลขผู้เสียภาษี %s) — ตอนยกจริงจะสร้างให้โดยคัดลอกจาก o14')
                         % (o14_partner, partner_vat.get(row['id']) or '-')))
        branch = cfg._map_branch(row.get('branch_id'))
        if row.get('branch_id') and not branch:
            head.append((WARN, _('ไม่พบสาขา "%s" ฝั่ง 18 ใบจะไม่มีสาขา') % row['branch_id'][1]))
        elif branch:
            head.append((OK, _('สาขา: %s') % branch.name))
        pricelist = cfg._map_pricelist(row.get('pricelist_id'), branch)
        o14_pl = (row.get('pricelist_id') or [0, ''])[1]
        pl_match = bool(pricelist) and cfg._pricelist_matches(row, pricelist)
        pl_name = pricelist.with_context(lang='th_TH').name if pricelist else '-'
        if pricelist and not pl_match:
            head.append((WARN, _('รายการราคา "%s" ไม่มีฝั่ง 18 ใช้ "%s" แทน — ราคาจะไม่ถูกยกตาม')
                         % (o14_pl, pl_name)))
        elif pricelist:
            head.append((OK, _('รายการราคา: %s → %s') % (o14_pl, pl_name)))
        o14_pids_all = {l['product_id'][0] for l in line_rows if l.get('product_id')}
        o14_prices = cfg._o14_pricelist_prices(row.get('pricelist_id'), o14_pids_all) if pl_match else {}
        o18_prices = {}
        if pl_match:
            for product, pid, _p14, p18 in cfg._pricelist_diffs(pricelist, o14_prices, code_index):
                o18_prices[pid] = p18
            n_change = sum(1 for pid, p in o14_prices.items()
                           if o18_prices.get(pid) is None or abs(o18_prices[pid] - p) > 0.0001)
            if n_change:
                head.append((WARN, _('ราคาในรายการราคา %s ไม่ตรง o14 %s สินค้า — ตอนยกจริงจะปรับให้ตรง o14')
                             % (pl_name, n_change)))

        existing = self.env['sale.order'].sudo().with_context(
            allowed_company_ids=cfg._all_companies()).search(
            [('o14_order_name', '=', row['name']), ('o14_source_db', '=', cfg.db_name)], limit=1)
        if existing:
            head.append((WARN, _('เคยยกมาแล้วเป็น %s — ยกอีกครั้งจะอัปเดตทับ') % existing.name))
        # ใช้เลขใบเดิมของ o14 — ต้องไม่ชนกับใบอื่นในบริษัทเดียวกันฝั่ง 18
        clash = cfg._name_clash(row)
        if clash:
            head.append((BAD, _('เลข %s ชนกับใบที่มีอยู่แล้วในบริษัทเดียวกันฝั่ง 18 (%s) ตัวยกจะกันไว้')
                         % (row['name'], clash.company_id.name)))
            ready = False
        else:
            others = self.env['sale.order'].sudo().with_context(
                allowed_company_ids=cfg._all_companies()).search(
                [('name', '=', row['name']), ('company_id', '!=', cfg.company_id.id)])
            note = _(' (มีเลขเดียวกันในบริษัทอื่น: %s — ปกติ เพราะแต่ละฐาน o14 รันเลขแยกกัน)') % \
                ', '.join(others.company_id.mapped('name')) if others else ''
            head.append((OK, _('ใช้เลขใบเดิม %s%s') % (row['name'], note)))

        # สินค้าที่ฝั่ง 18 ยังไม่มี: ตอนยกจริงจะสร้างให้ (คัดลอกจาก o14 + ลงสต็อกตาม o14)
        o14_pids = sorted({l['product_id'][0] for l in line_rows if l.get('product_id')})
        missing_ids = cfg._missing_o14_products(o14_pids, code_index)
        o14_qty = {}
        if missing_ids:
            o14_qty = {r['id']: r.get('qty_available') or 0.0 for r in cfg.execute_kw(
                'product.product', 'read', [missing_ids, ['qty_available']])}

        # รายบรรทัด: ไล่ให้ครบทุกบรรทัด ไม่หยุดที่บรรทัดแรกที่ติด
        line_ok = True
        for l in sorted(line_rows, key=lambda r: r.get('sequence') or 0):
            if l.get('display_type'):
                continue
            o14_prod = (l.get('product_id') or [0, '-'])[1]
            product = cfg._map_product(l.get('product_id'), code_index)
            o14_taxes = [tax_names.get(t, str(t)) for t in (l.get('tax_id') or []) if isinstance(t, int)]
            taxes = cfg._map_taxes(l.get('tax_id'), tax_names)
            icon = OK
            tax_text = '%s → %s' % (', '.join(o14_taxes) or '-', ', '.join(taxes.mapped('name')) or '-')
            if not product:
                icon = WARN
            else:
                conflict = cfg._product_name_conflict(o14_prod, product)
                if conflict:
                    icon = BAD
                    line_ok = False
                    head.append((BAD, _('รหัสเดียวกันแต่เป็นคนละสินค้า: ฝั่ง 14 "%s" / ฝั่ง 18 "%s" — ต้องแก้รหัสสินค้าก่อนยก')
                                 % (o14_prod, conflict)))
            pid = (l.get('product_id') or [0])[0]
            p14 = o14_prices.get(pid)
            p18 = o18_prices.get(pid)
            price_text = '-' if p14 is None else '%s → %s' % (
                '{:,.4f}'.format(p14), '-' if p18 is None else '{:,.4f}'.format(p18))
            if o14_taxes and len(taxes) < len(o14_taxes):
                icon = BAD
                line_ok = False
                tax_text += _(' (จับคู่ไม่ครบ)')
            items.append((icon, [o14_prod,
                                 product.display_name if product else _(
                                     'ยังไม่มี — ตอนยกจะสร้างให้ (คัดลอกจาก o14, สต็อก %s)') % '{:,.2f}'.format(
                                     o14_qty.get((l.get('product_id') or [0])[0], 0.0)),
                                 '{:,.2f}'.format(l.get('product_uom_qty') or 0),
                                 '{:,.4f}'.format(l.get('price_unit') or 0), price_text, tax_text]))
        if missing_ids:
            head.append((WARN, _('สินค้า %s ตัวยังไม่มีฝั่ง 18 — ตอนยกจริงจะสร้างให้โดยคัดลอกจาก o14 พร้อมลงสต็อกตาม o14')
                         % len(missing_ids)))
        if not line_ok:
            head.append((BAD, _('มีบรรทัดที่ติดปัญหา (ดูตารางด้านล่าง) ตัวยกจะกันใบนี้ไว้')))
            ready = False

        # ลองสร้างใบจริงใน savepoint แล้วย้อนทิ้ง เพื่อเทียบยอดกับฝั่ง 14
        if ready:
            diff, error = self._simulate(row, line_rows, partner, branch, code_index, tax_names)
            if error:
                head.append((BAD, _('ลองสร้างใบไม่ผ่าน: %s') % error))
                ready = False
            elif diff:
                head.append((BAD, _('ยอดไม่ตรงต้นทาง: %s') % diff))
                ready = False
            else:
                head.append((OK, _('ลองสร้างใบแล้ว ยอดตรงฝั่ง 14 ทุกบาท — พร้อมยก')))
        return head, items, ready

    def _simulate(self, row, line_rows, partner, branch, code_index, tax_names):
        cfg = self.config_id
        Order = self.env['sale.order'].sudo().with_context(
            allowed_company_ids=cfg._all_companies(), tracking_disable=True,
            mail_create_nolog=True, npd_no_line_tracking=True)
        result = {'diff': '', 'error': ''}
        try:
            with self.env.cr.savepoint():
                if not partner:
                    partner = cfg._ensure_partner_from_o14(row.get('partner_id'))
                values = cfg._prepare_order_values(row, partner, branch)
                pricelist = self.env['product.pricelist'].browse(values.get('pricelist_id'))
                if pricelist and cfg._pricelist_matches(row, pricelist):
                    pids = {l['product_id'][0] for l in line_rows if l.get('product_id')}
                    cfg._sync_pricelist_prices(pricelist, cfg._o14_pricelist_prices(
                        row.get('pricelist_id'), pids), code_index)
                # ตั้งชื่อเองเพื่อไม่ให้ไปดึงเลขลำดับใบเสนอราคาจริง
                values['name'] = 'ตรวจ-%s' % row['name']
                values['o14_order_name'] = False
                # สร้างสินค้าที่ขาดแบบเดียวกับตอนยกจริง (ย้อนทิ้งพร้อมใบทดลอง)
                o14_pids = sorted({l['product_id'][0] for l in line_rows if l.get('product_id')})
                _made, failed = cfg._ensure_products_from_o14(o14_pids, code_index)
                if failed:
                    raise UserError(_('สร้างสินค้าไม่ได้: %s') % '; '.join(failed))
                cmds = []
                for l in sorted(line_rows, key=lambda r: r.get('sequence') or 0):
                    lv, problem = cfg._prepare_line_values(l, code_index, tax_names)
                    if problem:
                        raise UserError(problem)
                    cmds.append((0, 0, lv))
                order = Order.create(dict(values, order_line=cmds))
                order.order_line._npd_normalize_vat_price()
                order.order_line.with_context(npd_skip_round=True)._npd_recalc_amounts()
                order.invalidate_recordset(['amount_untaxed', 'amount_tax', 'amount_total'])
                result['diff'] = cfg._compare_amounts(order, row, line_rows)
                raise _Rollback()
        except _Rollback:
            pass
        except Exception as error:  # noqa: BLE001 - แสดงให้ผู้ใช้เห็นว่าติดอะไร
            result['error'] = str(error)[:300]
        return result['diff'], result['error']


class RentalImportConfig(models.Model):
    _inherit = 'npd.rental.import.config'

    def action_open_check_wizard(self):
        self.ensure_one()
        wizard = self.env['npd.rental.import.check.wizard'].create({'config_id': self.id})
        return {
            'type': 'ir.actions.act_window', 'res_model': wizard._name, 'res_id': wizard.id,
            'view_mode': 'form', 'target': 'new', 'name': _('ตรวจ/ดึงรายใบ'),
        }

    def _tax_name_index(self, tax_ids):
        """ชื่อภาษีฝั่ง 14 ต่อ id — search_read ของ many2many ส่งมาแค่ id"""
        if not tax_ids:
            return {}
        rows = self.execute_kw('account.tax', 'read', [sorted(tax_ids), ['name']])
        return {r['id']: r['name'] for r in rows}
