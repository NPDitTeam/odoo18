# -*- coding: utf-8 -*-
"""ตัวยกข้อมูลงานเช่าจากฝั่ง Odoo 14

ออกแบบให้ **กดรันซ้ำได้** ทุกอย่างเป็น "สร้างถ้ายังไม่มี แก้ถ้ามีแล้ว"
เพราะฝั่ง 14 ยังใช้งานอยู่จนถึงวันย้ายจริง ข้อมูลที่ยกมาวันนี้จะล้าสมัย
พอถึงวันย้ายก็กดใหม่ทับได้เลย ไม่ต้องล้างของเก่าทิ้งก่อน
"""
import logging
import re
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
    # ยอดรายบรรทัด ใช้เทียบแทนยอดหัวใบ o14 ที่อาจค้าง
    'price_subtotal', 'price_tax', 'price_total',
]

# ช่องลูกค้าที่คัดลอกจาก o14 เมื่อฝั่ง 18 ยังไม่มีลูกค้ารายนี้
PARTNER_FIELDS = ['name', 'vat', 'is_company', 'street', 'street2', 'city', 'zip',
                  'phone', 'mobile', 'email', 'branch']


def product_name_key(name):
    """กุญแจเทียบชื่อสินค้าข้ามฐาน: ไม่สนตัวพิมพ์ ช่องว่าง ขีด และ "ชุด" ที่ o14 ใช้แทนขีด

    o14 มีชื่อที่ขีดกลายเป็นคำว่า "ชุด" เช่น "HชุดFrame" = "H-Frame", "250ชุด620" = "250-620"
    """
    text = (name or '').lower()
    if text.startswith('['):
        text = text.split(']', 1)[-1]
    # o14 มีสินค้าที่ถูกเปลี่ยนชื่อเป็น "... (สำเนา)" แต่เป็นตัวเดียวกับฝั่ง 18
    text = text.replace('(สำเนา)', '')
    text = re.sub(r'(?<=[0-9a-z.])ชุด(?=[0-9a-z(])', '-', text)
    return re.sub(r'[\s\-]+', '', text)


class _DryRun(Exception):
    """ใช้ย้อน savepoint ตอนทดลอง"""


class RentalImporter(models.Model):
    _inherit = 'npd.rental.import.config'

    def _o14_product_fields(self):
        """ช่องสินค้าที่ผู้ใช้เชื่อมต่อฝั่ง 14 อ่านได้จริง

        ผู้ใช้ที่ใช้เชื่อมต่อบางฐานไม่มีสิทธิ์ "Access to product costs" อ่าน standard_price
        แล้วทั้งคำสั่งล้ม — ตัดช่องที่อ่านไม่ได้ออก ดีกว่ายกสินค้าไม่ได้ทั้งหมด
        """
        available = set(self.execute_kw('product.template', 'fields_get', [[], ['type']]).keys())
        fields_ = [f for f in PRODUCT_FIELDS if f in available]
        try:
            self.execute_kw('product.template', 'search_read', [[], fields_], {'limit': 1})
        except Exception as error:  # noqa: BLE001
            if 'standard_price' not in str(error):
                raise
            fields_ = [f for f in fields_ if f != 'standard_price']
        return fields_

    def _template_from_o14_label(self, label):
        """สินค้าฝั่ง 18 จากป้าย "[รหัส] ชื่อ" ของ o14: รหัส (ที่ชื่อตรงกัน) ก่อน แล้วชื่อ"""
        Template = self.env['product.template'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False)
        code = label[1:label.find(']')] if label.startswith('[') and ']' in label else ''
        key = product_name_key(label)
        if code and not code.startswith('PR/'):
            found = Template.search([('default_code', '=', code)], limit=1)
            if found and any(product_name_key(found.with_context(lang=l).name) == key
                             for l in ('en_US', 'th_TH')):
                return found
        name = label.split(']', 1)[-1].strip() if label.startswith('[') else label
        head = name[:6]
        for cand in Template.search([('name', 'ilike', head)]) if head else []:
            if any(product_name_key(cand.with_context(lang=l).name) == key for l in ('en_US', 'th_TH')):
                return cand
        return Template.browse()

    def _product_name_conflict(self, o14_label, product):
        """รหัสตรงแต่เป็นคนละสินค้า — คืนชื่อฝั่ง 18 ที่ขัดกัน หรือค่าว่างถ้าตรงกัน"""
        if not product or not o14_label:
            return ''
        key14 = product_name_key(o14_label)
        names18 = {product.with_context(lang=l).name for l in ('th_TH', 'en_US')}
        if any(product_name_key(n) == key14 for n in names18 if n):
            return ''
        return product.with_context(lang='th_TH').name

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

    def _ensure_partner_from_o14(self, o14_value):
        """ลูกค้าที่ฝั่ง 18 ไม่มีจริง (ไม่เจอทั้งเลขผู้เสียภาษีและชื่อ) — คัดลอกจาก o14"""
        if not o14_value:
            return self.env['res.partner'].browse()
        o14_id = o14_value[0] if isinstance(o14_value, (list, tuple)) else o14_value
        available = set(self.execute_kw('res.partner', 'fields_get', [[], ['type']]).keys())
        rows = self.execute_kw('res.partner', 'read',
                               [[o14_id], [f for f in PARTNER_FIELDS if f in available]])
        if not rows:
            return self.env['res.partner'].browse()
        row = rows[0]
        Partner = self.env['res.partner'].sudo()
        values = {}
        for f in PARTNER_FIELDS:
            if f in row and f in Partner._fields and row[f] not in (False, None):
                values[f] = row[f].strip() if isinstance(row[f], str) else row[f]
        values['name'] = (values.get('name') or (o14_value[1] if isinstance(o14_value, (list, tuple)) else '')).strip()
        values['company_type'] = 'company' if row.get('is_company') else 'person'
        values.pop('is_company', None)
        # o18 บังคับเลขผู้เสียภาษีเป็นตัวเลข 13 หลักขึ้นไป (ไม่รู้ให้ใส่ 0000000000000)
        # เลขใน o14 ที่ไม่ผ่านกติกา เก็บของเดิมไว้ในหมายเหตุ ให้ฝ่ายขายตามแก้
        vat = values.get('vat') or ''
        if not (vat.isdigit() and len(vat) >= 13):
            if vat and 'comment' in Partner._fields:
                values['comment'] = _('เลขผู้เสียภาษีใน Odoo 14: %s (ไม่ผ่านกติกา 13 หลัก ต้องตามแก้)') % vat
            values['vat'] = '0000000000000'
        return Partner.with_context(skip_email_required=True).create(values)

    def _o14_pricelist_prices(self, o14_pricelist, o14_product_ids):
        """ราคาในรายการราคาของ o14 ต่อสินค้า (product.product id) — {id: ราคา}"""
        if not o14_pricelist or not o14_product_ids:
            return {}
        pl_id = o14_pricelist[0] if isinstance(o14_pricelist, (list, tuple)) else o14_pricelist
        prods = self.execute_kw('product.product', 'read', [sorted(o14_product_ids), ['product_tmpl_id']])
        tmpl_of = {p['id']: p['product_tmpl_id'][0] for p in prods if p.get('product_tmpl_id')}
        items = self.execute_kw('product.pricelist.item', 'search_read', [
            [('pricelist_id', '=', pl_id), ('product_tmpl_id', 'in', sorted(set(tmpl_of.values())))],
            ['product_tmpl_id', 'fixed_price']])
        price_of_tmpl = {i['product_tmpl_id'][0]: i.get('fixed_price') or 0.0 for i in items
                         if i.get('product_tmpl_id')}
        return {pid: price_of_tmpl[t] for pid, t in tmpl_of.items() if t in price_of_tmpl}

    def _pricelist_diffs(self, pricelist, o14_prices, code_index):
        """เทียบราคาในรายการราคาฝั่ง 18 กับ o14 — คืน [(product, ราคา o14, ราคา 18 หรือ None)]"""
        Item = self.env['product.pricelist.item'].sudo()
        out = []
        for pid, price in o14_prices.items():
            product = self._map_product([pid, ''], code_index)
            if not product:
                out.append((None, pid, price, None))
                continue
            item = Item.search([('pricelist_id', '=', pricelist.id),
                                ('product_tmpl_id', '=', product.product_tmpl_id.id)], limit=1)
            out.append((product, pid, price, item.fixed_price if item else None))
        return out

    def _sync_pricelist_prices(self, pricelist, o14_prices, code_index):
        """ตั้งราคาในรายการราคาฝั่ง 18 ให้ตรง o14 เฉพาะสินค้าที่ส่งมา — คืนจำนวนที่แก้/เพิ่ม"""
        Item = self.env['product.pricelist.item'].sudo()
        changed = 0
        for product, _pid, price, current in self._pricelist_diffs(pricelist, o14_prices, code_index):
            if not product:
                continue
            if current is None:
                Item.create({'pricelist_id': pricelist.id, 'applied_on': '1_product',
                             'product_tmpl_id': product.product_tmpl_id.id,
                             'compute_price': 'fixed', 'fixed_price': price})
                changed += 1
            elif abs(current - price) > 0.0001:
                Item.search([('pricelist_id', '=', pricelist.id),
                             ('product_tmpl_id', '=', product.product_tmpl_id.id)], limit=1).write(
                    {'fixed_price': price, 'compute_price': 'fixed'})
                changed += 1
        return changed

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
            allowed_company_ids=self._all_companies(), lang='th_TH')
        name = ((o14_value[1] if isinstance(o14_value, (list, tuple))
                 else o14_value) or '').strip()
        # ชื่อที่ได้จาก o14 เป็นชื่อแสดงผล ต่อท้ายสกุลเงิน "เรทเดือน (THB)" ต้องตัดออก
        if name.endswith(')') and '(' in name:
            name = name[:name.rfind('(')].strip()
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
        # รหัส PR/xxxxx ระบบแต่ละฐานออกเอง รหัสเดียวกันอีกฐานอาจเป็นคนละสินค้า
        # จึงไม่ใช้จับคู่ (ตรงกับปุ่มยกสินค้า ที่สร้างสินค้า PR/ โดยไม่ใส่รหัส)
        code = (o14_code_by_id or {}).get(o14_id)
        if code and not code.startswith('PR/'):
            found = Product.search([('default_code', '=', code)], limit=1)
            if found:
                return found
        # ป้ายฝั่ง 14 มาในรูป "[รหัส] ชื่อ" แกะรหัสออกมาใช้ก่อน
        if label.startswith('['):
            code = label[1:label.find(']')] if ']' in label else ''
            if code and not code.startswith('PR/'):
                found = Product.search([('default_code', '=', code)], limit=1)
                if found:
                    return found
            label = label.split(']', 1)[1].strip()
        found = Product.search([('name', '=', label.strip())], limit=1)
        if found:
            return found
        # ชื่อเขียนต่างกันเล็กน้อย (ตัวพิมพ์ ขีด/"ชุด") ใช้กุญแจชื่อเทียบ
        return self._template_from_o14_label(label).product_variant_id

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
            if not name:
                # ไม่รู้ชื่อภาษีต้นทาง ห้ามเดา (เดิมได้ภาษีขายตัวแรกของบริษัทมาแทน)
                continue
            found = Tax.search([('name', '=', name),
                                ('company_id', '=', self.company_id.id)], limit=1)
            if not found:
                found = Tax.search([('name', 'like', name.split()[0]),
                                    ('company_id', '=', self.company_id.id),
                                    ('type_tax_use', '=', 'sale')], limit=1)
            result |= found
        return result

    # ==================================================================
    # 1) สินค้า
    # ==================================================================
    def _find_template_for_o14(self, row):
        """สินค้าฝั่ง 18 ที่ตรงกับแถว product.template ของ o14 (รหัสจริงก่อน PR/ ใช้ชื่อ)"""
        Template = self.env['product.template'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False)
        code = (row.get('default_code') or '').strip()
        name = (row.get('name') or '').strip()
        if code and not code.startswith('PR/'):
            return Template.search([('default_code', '=', code)], limit=1)
        return Template.search([('name', '=', name)], limit=1)

    def _template_values_from_o14(self, row):
        """ค่าสินค้าฝั่ง 18 คัดลอกจากที่ตั้งไว้ใน o14 — คืน (values, ปัญหา)"""
        code = (row.get('default_code') or '').strip()
        name = (row.get('name') or '').strip()
        kind, storable = PRODUCT_TYPE_MAP.get(row.get('type'), ('consu', True))
        uom = self._map_uom(row.get('uom_id'))
        if not uom:
            return None, '%s (ไม่พบหน่วยนับ %s)' % (name, row.get('uom_id'))
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
        # รหัสที่ระบบออกให้เอง (PR/xxxxx) ไม่ตรงกันสองฝั่ง ไม่ใส่
        if code and not code.startswith('PR/'):
            values['default_code'] = code
        return values, None

    def _missing_o14_products(self, o14_product_ids, code_index):
        """id สินค้าฝั่ง 14 ที่ฝั่ง 18 ยังไม่มี"""
        return [pid for pid in o14_product_ids
                if not self._map_product([pid, ''], code_index)]

    def _ensure_products_from_o14(self, o14_product_ids, code_index):
        """สร้างสินค้าที่ใบเช่าใช้แต่ฝั่ง 18 ยังไม่มี โดยคัดลอกจาก o14 พร้อมลงสต็อกตาม o14

        คืน (สร้างแล้ว [ข้อความ], สร้างไม่ได้ [ข้อความ])
        """
        created, failed = [], []
        missing = self._missing_o14_products(o14_product_ids, code_index)
        if not missing:
            return created, failed
        prows = self.execute_kw('product.product', 'read',
                                [sorted(missing), ['product_tmpl_id', 'qty_available']])
        tmpl_ids = sorted({r['product_tmpl_id'][0] for r in prows if r.get('product_tmpl_id')})
        trows = {r['id']: r for r in self.execute_kw(
            'product.template', 'read', [tmpl_ids, self._o14_product_fields()])}
        Template = self.env['product.template'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False)
        for prow in prows:
            trow = trows.get(prow['product_tmpl_id'][0]) if prow.get('product_tmpl_id') else None
            if not trow:
                failed.append(_('อ่านสินค้า id %s จาก o14 ไม่ได้') % prow['id'])
                continue
            template = self._find_template_for_o14(trow)
            if not template:
                values, problem = self._template_values_from_o14(trow)
                if problem:
                    failed.append(problem)
                    continue
                template = Template.create(values)
            qty = prow.get('qty_available') or 0.0
            if template.is_storable:
                self._set_stock_qty(template.product_variant_id, qty)
            created.append(_('%s %s (สต็อกตาม o14 %s)') % (
                trow.get('default_code') or '-', trow.get('name'),
                '{:,.2f}'.format(qty) if template.is_storable else '-'))
        return created, failed

    def _set_stock_qty(self, product, qty):
        """ตั้งยอดคงเหลือในคลังหลักของบริษัทปลายทาง = qty"""
        warehouse = self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_('บริษัท %s ยังไม่มีคลังสินค้าฝั่ง 18') % self.company_id.name)
        location = warehouse.lot_stock_id
        Quant = self.env['stock.quant'].sudo().with_context(
            inventory_mode=True, allowed_company_ids=self._all_companies())
        quant = Quant.search([('product_id', '=', product.id),
                              ('location_id', '=', location.id)], limit=1)
        if quant:
            quant.write({'inventory_quantity': qty})
        else:
            quant = Quant.create({'product_id': product.id, 'location_id': location.id,
                                  'inventory_quantity': qty})
        quant.action_apply_inventory()
    def action_sync_products(self, dry_run=False):
        """ยกสินค้าเช่าให้ตรงฝั่ง 14 — จับคู่ด้วย "ชื่อ" ก่อน แล้วแก้รหัสฝั่ง 18 ให้ตรง o14

        เดิมจับคู่ด้วยรหัสแล้วเขียนทับทั้งตัว แต่รหัสฝั่ง 18 หลายตัวไม่ตรง o14
        (เช่นชุด REE-0133..0152 เลื่อนไป 1) การเขียนทับตามรหัสจะเปลี่ยนสินค้าที่ใบเช่า/สต็อก
        ฝั่ง 18 ผูกอยู่ให้กลายเป็นคนละขนาด จึงยึดชื่อเป็นตัวตน แล้วย้ายรหัสให้ถูกแทน

        * ชื่อตรง (ไม่สนตัวพิมพ์/ช่องว่าง/ขีด) → แก้รหัสให้ตรง o14 + ราคา/ต้นทุน/หมวด
          (ไม่แก้ชื่อ ไม่แก้หน่วยนับ: สินค้าที่มีสต็อกแล้ว Odoo ไม่ให้เปลี่ยนหน่วย)
        * ไม่เจอชื่อ → สร้างใหม่ ถ้ารหัสถูกสินค้าอื่นฝั่ง 18 ถืออยู่และไม่ได้ถูกย้ายออก → ข้าม+รายงาน
        dry_run=True ทำทุกอย่างแล้วย้อนทิ้ง คืนรายงานอย่างเดียว
        """
        self.ensure_one()
        fields_ = self._o14_product_fields()
        rows = self.search_read_all(
            'product.template',
            [('name', 'like', '(R)')], fields_)
        Template = self.env['product.template'].sudo().with_context(
            allowed_company_ids=self._all_companies(), active_test=False, lang='en_US')
        all18 = Template.search([])
        by_key = {}
        for tmpl in all18:
            for lang in ('en_US', 'th_TH'):
                key = product_name_key(tmpl.with_context(lang=lang).name)
                if key:
                    by_key.setdefault(key, tmpl)
        by_code = {(t.default_code or '').strip(): t for t in all18 if t.default_code}

        recode, update, create, skipped, conflicts = [], [], [], [], []
        claimed = set()
        for row in rows:
            code = (row.get('default_code') or '').strip()
            usable = bool(code) and not code.startswith('PR/')
            values, problem = self._template_values_from_o14(row)
            if problem:
                skipped.append(problem)
                continue
            tmpl = by_key.get(product_name_key(row.get('name')))
            if tmpl and tmpl.id in claimed:
                skipped.append(_('%s %s (ชื่อซ้ำกับสินค้าอื่นในฝั่ง 14)') % (code or '-', row.get('name')))
                continue
            if tmpl:
                claimed.add(tmpl.id)
                if usable and (tmpl.default_code or '') != code:
                    recode.append((tmpl, tmpl.default_code or '', code, row.get('name')))
                update.append((tmpl, values))
            else:
                create.append((row, values, code if usable else ''))

        # รหัสปลายทางต้องว่าง: ถือโดยสินค้าที่ถูกย้ายรหัสออกไปเองในรอบนี้ หรือไม่มีใครถือ
        moving = {r[0].id for r in recode}
        final_recode = []
        for tmpl, old, new, name in recode:
            holder = by_code.get(new)
            if holder and holder.id != tmpl.id and holder.id not in moving:
                conflicts.append(_('%s: "%s" ใช้รหัสนี้อยู่แล้ว ฝั่ง 18 จะย้ายให้ "%s" ไม่ได้')
                                 % (new, holder.name, name))
                continue
            final_recode.append((tmpl, old, new, name))
        final_create = []
        taken = {new for _t, _o, new, _n in final_recode}
        for row, values, code in create:
            holder = by_code.get(code) if code else None
            if code and ((holder and holder.id not in moving) or code in taken):
                conflicts.append(_('%s: สร้าง "%s" ไม่ได้ เพราะรหัสนี้เป็นของ "%s" ฝั่ง 18')
                                 % (code, row.get('name'), holder.name if holder else '?'))
                continue
            final_create.append((row, values, code))

        try:
            with self.env.cr.savepoint():
                # ย้ายรหัส 2 จังหวะ กันชนกันเองระหว่างย้าย (เช่น 0151→0152 ขณะที่ 0152→0144)
                for tmpl, _old, _new, _name in final_recode:
                    tmpl.write({'default_code': 'TMP-%s' % tmpl.id})
                for tmpl, _old, new, _name in final_recode:
                    tmpl.write({'default_code': new})
                # สินค้าที่มีอยู่แล้วแก้แค่รหัส: หมวดสินค้ากำหนดบัญชีที่ใช้ลง และราคาตั้งต้นแต่ละฐาน o14
                # ไม่เท่ากัน ยกทีละฐานจะเขียนทับกันไปมา (ราคาเช่าจริงอยู่ในรายการราคา ยกแยก)
                for row, values, code in final_create:
                    values = dict(values)
                    if code:
                        values['default_code'] = code
                    else:
                        values.pop('default_code', None)
                    Template.create(values)
                if dry_run:
                    raise _DryRun()
        except _DryRun:
            pass

        head = _('ทดลอง (ไม่บันทึก) — ') if dry_run else ''
        text = head + (_('สินค้าเช่า %s: ฝั่ง 14 มี %s ตัว | มีแล้วฝั่ง 18 %s | แก้รหัสให้ตรง o14 %s | '
                         'สร้างใหม่ %s | ข้าม %s | รหัสชนกัน %s')
                       % (self.db_name, len(rows), len(update), len(final_recode),
                          len(final_create), len(skipped), len(conflicts)))
        if final_recode:
            text += '\n' + _('แก้รหัส (รหัสเดิมฝั่ง 18 → รหัส o14):') + '\n  ' + '\n  '.join(
                '%s → %s  %s' % (old or '-', new, name) for _t, old, new, name in final_recode)
        if final_create:
            text += '\n' + _('สร้างใหม่:') + '\n  ' + '\n  '.join(
                '%s %s' % (code or '-', row.get('name')) for row, _v, code in final_create)
        if conflicts:
            text += '\n' + _('รหัสชนกัน (ข้าม ต้องตัดสินเอง):') + '\n  ' + '\n  '.join(conflicts)
        if skipped:
            text += '\n' + _('ข้าม:') + '\n  ' + '\n  '.join(skipped[:30])
        if not dry_run:
            self._note(text)
        return text

    # ==================================================================
    # 2) รายการราคา
    # ==================================================================
    def action_sync_pricelists(self, dry_run=False):
        """ยกราคาต่อสาขาให้ตรงฝั่ง 14

        ฝั่ง 14 ตั้งชื่อรายการราคาซ้ำกันทุกสาขา ("เรทวัน"/"เรทเดือน") แล้วแยก
        ด้วยช่องสาขา ส่วนฝั่ง 18 เอาชื่อสาขาต่อท้ายชื่อรายการ จึงต้องแปลงชื่อ
        (ชื่อภาษาอังกฤษฝั่ง 18 บางรายการไม่มีชื่อสาขา จึงค้นเป็นภาษาไทย และตัดช่องว่างท้าย)
        dry_run=True ทำแล้วย้อนทิ้ง คืนรายงานอย่างเดียว
        """
        self.ensure_one()
        lists14 = self.search_read_all(
            'product.pricelist', [], ['name', 'pricelist_branch_id', 'currency_id'])
        Pricelist = self.env['product.pricelist'].sudo().with_context(
            allowed_company_ids=self._all_companies(), lang='th_TH')
        Item = self.env['product.pricelist.item'].sudo()

        made, changed, same, missing_products, missing_lists = 0, 0, 0, [], []
        try:
            with self.env.cr.savepoint():
                for row in lists14:
                    branch = self._map_branch(row.get('pricelist_branch_id'))
                    if not branch:
                        missing_lists.append('%s (ไม่พบสาขา %s)'
                                             % (row['name'], row.get('pricelist_branch_id')))
                        continue
                    target_name = '%s %s' % (row['name'].strip(), branch.name.strip())
                    pricelist = Pricelist.search([('name', '=', target_name)], limit=1)
                    if not pricelist:
                        pricelist = Pricelist.search([('name', 'ilike', target_name)]).filtered(
                            lambda pl: ' '.join(pl.name.split()) == ' '.join(target_name.split()))[:1]
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
                        label = tmpl_ref[1] if isinstance(tmpl_ref, (list, tuple)) else ''
                        name = label.split(']', 1)[-1].strip() if label.startswith('[') else label
                        template = self._template_from_o14_label(label)
                        if not template:
                            missing_products.append(name)
                            continue
                        price = item.get('fixed_price') or 0.0
                        found = existing.get(template.id)
                        if found:
                            if abs((found.fixed_price or 0.0) - price) > 0.0001:
                                found.write({'fixed_price': price, 'compute_price': 'fixed'})
                                changed += 1
                            else:
                                same += 1
                        else:
                            existing[template.id] = Item.create({
                                'pricelist_id': pricelist.id,
                                'applied_on': '1_product',
                                'product_tmpl_id': template.id,
                                'compute_price': 'fixed',
                                'fixed_price': price,
                                'min_quantity': item.get('min_quantity') or 0,
                            })
                            made += 1
                if dry_run:
                    raise _DryRun()
        except _DryRun:
            pass

        head = _('ทดลอง (ไม่บันทึก) — ') if dry_run else ''
        text = head + (_('รายการราคา %s: ฝั่ง 14 มี %s รายการ | เพิ่มราคา %s | แก้ราคา %s | ตรงอยู่แล้ว %s')
                       % (self.db_name, len(lists14), made, changed, same))
        if missing_lists:
            text += '\n' + _('รายการที่จับคู่ไม่ได้:') + '\n  ' \
                + '\n  '.join(sorted(set(missing_lists))[:30])
        if missing_products:
            text += '\n' + _('สินค้าที่ยังไม่มีฝั่ง 18 (%s ตัว) — กดยกสินค้าก่อน:') \
                % len(set(missing_products)) + '\n  ' \
                + '\n  '.join(sorted(set(missing_products))[:30])
        if not dry_run:
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
