# -*- coding: utf-8 -*-
"""ตัวยกข้อมูลงานเช่าจากฝั่ง Odoo 14

ออกแบบให้ **กดรันซ้ำได้** ทุกอย่างเป็น "สร้างถ้ายังไม่มี แก้ถ้ามีแล้ว"
เพราะฝั่ง 14 ยังใช้งานอยู่จนถึงวันย้ายจริง ข้อมูลที่ยกมาวันนี้จะล้าสมัย
พอถึงวันย้ายก็กดใหม่ทับได้เลย ไม่ต้องล้างของเก่าทิ้งก่อน
"""
import logging
from datetime import date

from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# o14 เก็บชนิดสินค้าเป็น product/consu/service ส่วน o18 ยุบเหลือ consu/service
# แล้วแยก "นับสต็อกไหม" ออกมาเป็นช่องต่างหาก
PRODUCT_TYPE_MAP = {
    'product': ('consu', True),
    'consu': ('consu', False),
    'service': ('service', False),
}

PRODUCT_FIELDS = [
    'name', 'default_code', 'type', 'uom_id', 'uom_po_id', 'categ_id',
    'list_price', 'standard_price', 'sale_ok', 'purchase_ok', 'barcode',
]

ORDER_FIELDS = [
    'name', 'partner_id', 'date_order', 'state', 'branch_id',
    # ช่องบังคับกรอกของฝั่ง 18 ถ้าไม่ส่งไปจะติด NOT NULL ตอนบันทึก
    'contact_type', 'delivery_type', 'on_site', 'pfb_so_type',
    'customer_channel_id', 'pricelist_id', 'partner_invoice_id',
    'partner_shipping_id', 'picking_policy', 'user_id',
    'npd_so_type', 'renewal_bill_status', 'deposit_ref', 'rental_status',
    'start_rent_date', 'end_rent_date', 'pfb_date_of_rent',
    'rental_contract_no', 'rental_contract_prefix', 'is_in_rent',
    'total_rental_discount', 'deposit_return_status',
    'use_new_calc', 'use_baan_kheaw', 'vat_from_total',
    'x_round_enabled', 'x_round_step', 'x_round_method',
    'amount_untaxed', 'amount_tax', 'amount_total', 'note', 'client_order_ref',
]

LINE_FIELDS = [
    'product_id', 'name', 'product_uom_qty', 'product_uom', 'price_unit',
    'discount', 'tax_id', 'sequence', 'display_type',
]


class RentalImporter(models.Model):
    _inherit = 'npd.rental.import.config'

    # ==================================================================
    # ตัวช่วยจับคู่ข้ามฐาน
    # ==================================================================
    def _all_companies(self):
        """ต้องมองข้ามบริษัทเสมอ ไม่งั้นหาของที่อยู่คนละบริษัทไม่เจอ"""
        return self.env['res.company'].sudo().search([]).ids

    def _map_uom(self, o14_value):
        if not o14_value:
            return self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
        name = o14_value[1] if isinstance(o14_value, (list, tuple)) else o14_value
        return self.env['uom.uom'].sudo().search([('name', '=', name)], limit=1)

    def _map_category(self, o14_value):
        Categ = self.env['product.category'].sudo()
        if not o14_value:
            return Categ.search([], limit=1)
        name = o14_value[1] if isinstance(o14_value, (list, tuple)) else o14_value
        # ชื่อหมวดฝั่ง 14 มาเป็นเส้นทางเต็ม "แม่ / ลูก" เอาชื่อท้ายมาจับคู่
        leaf = name.split('/')[-1].strip()
        categ = Categ.search([('name', '=', leaf)], limit=1)
        return categ or Categ.create({'name': leaf})

    def _map_branch(self, o14_value):
        if not o14_value:
            return self.env['res.branch'].sudo().browse()
        name = o14_value[1] if isinstance(o14_value, (list, tuple)) else o14_value
        return self.env['res.branch'].sudo().search(
            [('name', '=', name.strip())], limit=1)

    def _map_partner(self, o14_value, vat=None):
        """จับคู่ลูกค้า — เลขผู้เสียภาษีก่อน แล้วค่อยชื่อ

        ชื่อสองฝั่งไม่ตรงกันบ่อยเพราะฝั่ง 14 ต่อท้าย "(สำนักงานใหญ่)" ไว้
        ส่วนเลขผู้เสียภาษีเป็นเลขราชการ นิติบุคคลเดียวกันต้องตรงกันเสมอ
        ไม่สร้างลูกค้าใหม่เองถ้าหาไม่เจอ เพราะลูกค้าซ้ำแก้ยากกว่าหาไม่เจอมาก
        """
        Partner = self.env['res.partner'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False)
        if vat:
            found = Partner.search([('vat', '=', vat.strip())], limit=2)
            if found:
                return found[0]
        if not o14_value:
            return Partner.browse()
        name = (o14_value[1] if isinstance(o14_value, (list, tuple))
                else o14_value).strip()
        for candidate in (name, self._strip_branch_suffix(name)):
            if not candidate:
                continue
            found = Partner.search([('name', '=', candidate)], limit=2)
            if len(found) == 1:
                return found
            if len(found) > 1:
                same = found.filtered(lambda p: p.company_id == self.company_id
                                      or not p.company_id)
                return (same or found)[0]
        return Partner.browse()

    @staticmethod
    def _strip_branch_suffix(name):
        """ตัดวงเล็บท้ายชื่อนิติบุคคลออก เช่น "(สำนักงานใหญ่)" หรือ "(สาขาที่ 1)" """
        text = (name or '').strip()
        if text.endswith(')') and '(' in text:
            head = text[:text.rfind('(')].strip()
            tail = text[text.rfind('('):]
            if 'สำนักงานใหญ่' in tail or 'สาขา' in tail:
                return head
        return text

    def _map_channel(self, o14_value):
        """ช่องทางลูกค้า — ฝั่ง 18 บังคับกรอก แต่รายการสองฝั่งไม่เหมือนกัน

        สร้างตามชื่อฝั่ง 14 ให้เลย ดีกว่ายัดค่าสุ่มแล้วรายงานการตลาดเพี้ยน
        """
        Channel = self.env['customer.channel'].sudo()
        if not o14_value:
            fallback = Channel.search([('name', '=', 'ยกมาจาก Odoo 14')], limit=1)
            return fallback or Channel.create({'name': 'ยกมาจาก Odoo 14'})
        name = (o14_value[1] if isinstance(o14_value, (list, tuple))
                else o14_value).strip()
        found = Channel.search([('name', '=', name)], limit=1)
        return found or Channel.create({'name': name})

    def _map_pricelist(self, o14_value, branch):
        """รายการราคา — ฝั่ง 14 ชื่อซ้ำทุกสาขา ฝั่ง 18 เอาชื่อสาขาต่อท้าย"""
        Pricelist = self.env['product.pricelist'].sudo().with_context(
            allowed_company_ids=self._all_companies())
        name = ((o14_value[1] if isinstance(o14_value, (list, tuple))
                 else o14_value) or '').strip()
        if name and branch:
            found = Pricelist.search(
                [('name', '=', '%s %s' % (name, branch.name))], limit=1)
            if found:
                return found
        if name:
            found = Pricelist.search([('name', '=', name)], limit=1)
            if found:
                return found
        return Pricelist.search(
            [('company_id', 'in', (False, self.company_id.id))], limit=1)

    def _map_product(self, o14_value, o14_code_by_id=None):
        """จับคู่สินค้าด้วยรหัสก่อน แล้วค่อยชื่อ — รหัสเชื่อถือได้กว่า"""
        if not o14_value:
            return self.env['product.product'].sudo().browse()
        o14_id = o14_value[0] if isinstance(o14_value, (list, tuple)) else o14_value
        label = o14_value[1] if isinstance(o14_value, (list, tuple)) else ''
        Product = self.env['product.product'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False)
        code = (o14_code_by_id or {}).get(o14_id)
        if code:
            found = Product.search([('default_code', '=', code)], limit=1)
            if found:
                return found
        # ป้ายฝั่ง 14 มาในรูป "[รหัส] ชื่อ" แกะรหัสออกมาใช้ก่อน
        if label.startswith('['):
            code = label[1:label.find(']')] if ']' in label else ''
            if code:
                found = Product.search([('default_code', '=', code)], limit=1)
                if found:
                    return found
            label = label.split(']', 1)[1].strip()
        return Product.search([('name', '=', label.strip())], limit=1)

    def _map_taxes(self, o14_values, o14_tax_names=None):
        """ภาษีต้องเป็นของบริษัทเดียวกัน ไม่งั้น Odoo ตีกลับตอนบันทึก"""
        if not o14_values:
            return self.env['account.tax'].sudo().browse()
        Tax = self.env['account.tax'].sudo()
        result = Tax.browse()
        for value in o14_values:
            tax_id = value[0] if isinstance(value, (list, tuple)) else value
            name = (value[1] if isinstance(value, (list, tuple))
                    else (o14_tax_names or {}).get(tax_id, ''))
            found = Tax.search([('name', '=', name),
                                ('company_id', '=', self.company_id.id)], limit=1)
            if not found:
                found = Tax.search([('name', 'like', name.split()[0] if name else ''),
                                    ('company_id', '=', self.company_id.id),
                                    ('type_tax_use', '=', 'sale')], limit=1)
            result |= found
        return result

    # ==================================================================
    # 1) สินค้า
    # ==================================================================
    def action_sync_products(self):
        """สร้างสินค้าเช่าที่ฝั่ง 18 ยังไม่มี — จับคู่ด้วยรหัสสินค้า"""
        self.ensure_one()
        rows = self.search_read_all(
            'product.template',
            [('name', 'like', '(R)')], PRODUCT_FIELDS)
        Template = self.env['product.template'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False)
        created, updated, skipped = [], [], []
        for row in rows:
            code = (row.get('default_code') or '').strip()
            name = (row.get('name') or '').strip()
            # รหัสที่ระบบออกให้เอง (PR/xxxxx) ไม่ตรงกันสองฝั่ง ใช้ชื่อแทน
            usable_code = code and not code.startswith('PR/')
            domain = ([('default_code', '=', code)] if usable_code
                      else [('name', '=', name)])
            existing = Template.search(domain, limit=1)
            kind, storable = PRODUCT_TYPE_MAP.get(row.get('type'), ('consu', True))
            uom = self._map_uom(row.get('uom_id'))
            if not uom:
                skipped.append('%s (ไม่พบหน่วยนับ %s)' % (name, row.get('uom_id')))
                continue
            values = {
                'name': name,
                'type': kind,
                'is_storable': storable,
                'uom_id': uom.id,
                'uom_po_id': (self._map_uom(row.get('uom_po_id')) or uom).id,
                'categ_id': self._map_category(row.get('categ_id')).id,
                'list_price': row.get('list_price') or 0.0,
                'standard_price': row.get('standard_price') or 0.0,
                'sale_ok': bool(row.get('sale_ok')),
                'purchase_ok': bool(row.get('purchase_ok')),
            }
            if usable_code:
                values['default_code'] = code
            if existing:
                existing.write(values)
                updated.append(name)
            else:
                Template.create(values)
                created.append('%s %s' % (code or '-', name))
        text = (_('สินค้าเช่า: ฝั่ง 14 มี %s ตัว | สร้างใหม่ %s | อัปเดต %s | ข้าม %s')
                % (len(rows), len(created), len(updated), len(skipped)))
        if created:
            text += '\n' + _('สร้างใหม่:') + '\n  ' + '\n  '.join(created[:50])
        if skipped:
            text += '\n' + _('ข้าม:') + '\n  ' + '\n  '.join(skipped[:20])
        self._note(text)
        return text

    # ==================================================================
    # 2) รายการราคา
    # ==================================================================
    def action_sync_pricelists(self):
        """ยกราคาต่อสาขาให้ตรงฝั่ง 14

        ฝั่ง 14 ตั้งชื่อรายการราคาซ้ำกันทุกสาขา ("เรทวัน"/"เรทเดือน") แล้วแยก
        ด้วยช่องสาขา ส่วนฝั่ง 18 เอาชื่อสาขาต่อท้ายชื่อรายการ จึงต้องแปลงชื่อ
        """
        self.ensure_one()
        lists14 = self.search_read_all(
            'product.pricelist', [], ['name', 'pricelist_branch_id', 'currency_id'])
        Pricelist = self.env['product.pricelist'].sudo().with_context(
            allowed_company_ids=self._all_companies())
        Item = self.env['product.pricelist.item'].sudo()
        Template = self.env['product.template'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False)

        made, changed, missing_products, missing_lists = 0, 0, [], []
        for row in lists14:
            branch = self._map_branch(row.get('pricelist_branch_id'))
            if not branch:
                missing_lists.append('%s (ไม่พบสาขา %s)'
                                     % (row['name'], row.get('pricelist_branch_id')))
                continue
            target_name = '%s %s' % (row['name'], branch.name)
            pricelist = Pricelist.search([('name', '=', target_name)], limit=1)
            if not pricelist:
                missing_lists.append(_('ไม่พบรายการราคา "%s" ฝั่ง 18') % target_name)
                continue

            items14 = self.search_read_all(
                'product.pricelist.item', [('pricelist_id', '=', row['id'])],
                ['product_tmpl_id', 'fixed_price', 'applied_on', 'min_quantity'])
            existing = {i.product_tmpl_id.id: i
                        for i in Item.search([('pricelist_id', '=', pricelist.id)])
                        if i.product_tmpl_id}
            for item in items14:
                tmpl_ref = item.get('product_tmpl_id')
                if not tmpl_ref:
                    continue
                name = tmpl_ref[1] if isinstance(tmpl_ref, (list, tuple)) else ''
                if name.startswith('['):
                    name = name.split(']', 1)[-1].strip()
                template = Template.search([('name', '=', name)], limit=1)
                if not template:
                    missing_products.append(name)
                    continue
                price = item.get('fixed_price') or 0.0
                found = existing.get(template.id)
                if found:
                    if abs((found.fixed_price or 0.0) - price) > 0.0001:
                        found.write({'fixed_price': price,
                                     'compute_price': 'fixed'})
                        changed += 1
                else:
                    Item.create({
                        'pricelist_id': pricelist.id,
                        'applied_on': '1_product',
                        'product_tmpl_id': template.id,
                        'compute_price': 'fixed',
                        'fixed_price': price,
                        'min_quantity': item.get('min_quantity') or 0,
                    })
                    made += 1

        text = (_('รายการราคา: ฝั่ง 14 มี %s รายการ | เพิ่มราคา %s | แก้ราคา %s')
                % (len(lists14), made, changed))
        if missing_lists:
            text += '\n' + _('รายการที่จับคู่ไม่ได้:') + '\n  ' \
                + '\n  '.join(sorted(set(missing_lists))[:20])
        if missing_products:
            text += '\n' + _('สินค้าที่ยังไม่มีฝั่ง 18 (%s ตัว) — กดยกสินค้าก่อน:') \
                % len(set(missing_products)) + '\n  ' \
                + '\n  '.join(sorted(set(missing_products))[:20])
        self._note(text)
        return text

    # ==================================================================
    # 3) สต็อก
    # ==================================================================
    def action_sync_stock(self, product_codes=None):
        """ปรับยอดคงเหลือให้ตรงฝั่ง 14

        ยอดฝั่ง 14 หักของที่ถูกเช่าออกไปแล้ว จึงเอามาใช้ได้ตรง ๆ
        ไม่ต้องไปไล่คำนวณว่าอะไรอยู่ที่ลูกค้าบ้าง
        """
        self.ensure_one()
        domain = [('name', 'like', '(R)'), ('type', '=', 'product')]
        rows = self.search_read_all('product.product', domain,
                                    ['default_code', 'name', 'qty_available'])
        if product_codes:
            wanted = set(product_codes)
            rows = [r for r in rows
                    if (r.get('default_code') or '') in wanted]
        warehouse = self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_('บริษัท %s ยังไม่มีคลังสินค้าฝั่ง 18')
                            % self.company_id.name)
        location = warehouse.lot_stock_id
        Quant = self.env['stock.quant'].sudo().with_context(
            inventory_mode=True, allowed_company_ids=self._all_companies())
        Product = self.env['product.product'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False)

        done, missing = 0, []
        for row in rows:
            code = (row.get('default_code') or '').strip()
            product = Product.search([('default_code', '=', code)], limit=1) \
                if code and not code.startswith('PR/') else Product.browse()
            if not product:
                product = Product.search([('name', '=', row['name'])], limit=1)
            if not product:
                missing.append('%s %s' % (code or '-', row['name']))
                continue
            qty = row.get('qty_available') or 0.0
            quant = Quant.search([('product_id', '=', product.id),
                                  ('location_id', '=', location.id)], limit=1)
            if quant:
                quant.write({'inventory_quantity': qty})
            else:
                quant = Quant.create({
                    'product_id': product.id,
                    'location_id': location.id,
                    'inventory_quantity': qty,
                })
            quant.action_apply_inventory()
            done += 1
        text = (_('สต็อก: ปรับยอดให้ตรงฝั่ง 14 แล้ว %s ตัว จากที่ฝั่ง 14 มี %s ตัว')
                % (done, len(rows)))
        if missing:
            text += '\n' + _('ยังไม่มีสินค้านี้ฝั่ง 18 (%s ตัว):') % len(missing) \
                + '\n  ' + '\n  '.join(missing[:20])
        self._note(text)
        return text
