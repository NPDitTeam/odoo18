# -*- coding: utf-8 -*-
"""ราคาใบเช่าแบบ Odoo 14 — พิมพ์ราคาไม่รวม VAT แล้วคิด ราคาไม่รวม VAT x จำนวน + 7%

ช่อง "ราคาต่อหน่วย" (price_unit_no_vat) = ราคาไม่รวม VAT ที่พนักงานพิมพ์
ระบบเก็บ price_unit = ราคารวม VAT = ราคาไม่รวม VAT x 1.07 แบบไม่ปัด (ทศนิยม 4 ตำแหน่ง)
เช่น 1.20 -> 1.2840 ภาษีรวมในราคา + ปัดทั้งใบ จึงได้ยอดตรงกับ o14 ด้วยสูตรมาตรฐานของ Odoo
(1.2840 x 10,920 = 14,021.28 ก่อน VAT 13,104.00) และใบแจ้งหนี้ที่ก็อปราคาไปก็ได้ยอดเดียวกัน

เดิม (o14 และ o18 รุ่นแรก) ปัดราคารวม VAT เหลือ 2 ตำแหน่ง (1.28) แล้วต้องมีสูตรพิเศษ
ถอดกลับทีละบรรทัด + เขียนยอดหัวใบด้วย SQL — เลิกใช้แล้ว ใช้สูตรมาตรฐานทั้งหมด
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

VAT_RATE = 0.07


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    use_new_calc = fields.Boolean(
        related='order_id.use_new_calc', store=True, readonly=True)
    use_baan_kheaw = fields.Boolean(
        related='order_id.use_baan_kheaw', store=True, readonly=True)
    vat_from_total = fields.Boolean(
        related='order_id.vat_from_total', store=True, readonly=True)

    price_unit_no_vat = fields.Float(
        string='ราคาต่อหน่วย (ถอด VAT)',
        compute='_compute_price_unit_no_vat',
        inverse='_inverse_price_unit_no_vat',
        store=False, digits=(16, 2))

    # ------------------------------------------------------------------
    def _npd_use_method_a(self):
        """บรรทัดนี้เข้าเงื่อนไข Method A ไหม

        ต้องอ่านธงจาก order_id ตรง ๆ ไม่ผ่าน related เพราะระหว่างอยู่ในฟอร์ม
        ค่า related ยังเป็นของเดิม จะได้ผลไม่ตรงกับที่ผู้ใช้เห็น
        """
        self.ensure_one()
        order = self.order_id
        if not order or order.use_baan_kheaw:
            return False
        use_new_calc = order.use_new_calc
        if not use_new_calc and not order._origin and 'use_new_calc' not in order._cache:
            # ใบใหม่ที่ยังไม่บันทึก หน้าจออาจไม่ส่งค่าธงหัวใบมาให้บรรทัด → ใช้ค่าตั้งต้นของฟิลด์
            use_new_calc = order._fields['use_new_calc'].default(order)
        if not use_new_calc:
            return False
        return bool(self.tax_id) and any(
            tax.price_include and abs(tax.amount - 7.0) < 0.01
            for tax in self.tax_id)

    @api.depends('price_unit', 'tax_id',
                 'order_id.use_new_calc', 'order_id.use_baan_kheaw')
    def _compute_price_unit_no_vat(self):
        for line in self:
            line.price_unit_no_vat = (
                round(line.price_unit / 1.07, 2)
                if line._npd_use_method_a() else line.price_unit)

    def _npd_price_unit_from_no_vat(self):
        """ค่าที่ควรเขียนกลับลง price_unit — None = ไม่ต้องเขียน

        ถ้าค่าที่ได้ตรงกับผลคำนวณเดิมอยู่แล้ว แปลว่าเกิดจากการสลับธง
        ไม่ใช่ผู้ใช้พิมพ์เอง ต้องไม่เขียนกลับ ไม่งั้นราคาจะเพี้ยนทีละนิด
        """
        self.ensure_one()
        if self._npd_use_method_a():
            expected = round(self.price_unit / 1.07, 2)
            if abs(self.price_unit_no_vat - expected) < 0.001:
                return None
            # ไม่ปัดเหลือ 2 ตำแหน่ง — 1.20 x 1.07 = 1.284 ต้องเก็บ 1.2840 ไม่ใช่ 1.28
            return round(self.price_unit_no_vat * 1.07, 4)
        if abs(self.price_unit_no_vat - self.price_unit) < 0.001:
            return None
        return self.price_unit_no_vat

    def _inverse_price_unit_no_vat(self):
        for line in self:
            new_price = line._npd_price_unit_from_no_vat()
            if new_price is not None and abs(line.price_unit - new_price) > 0.001:
                line.price_unit = new_price

    @api.onchange('price_unit_no_vat')
    def _onchange_price_unit_no_vat(self):
        for line in self:
            new_price = line._npd_price_unit_from_no_vat()
            if new_price is not None and line.price_unit != new_price:
                line.price_unit = new_price

    # ------------------------------------------------------------------
    def _npd_normalize_vat_price(self):
        """แปลงราคารวม VAT ที่ปัด 2 ตำแหน่งแบบเก่า (o14 / ใบ o18 ก่อน 8 ต.ค. 2569)
        เป็นราคาไม่ปัด เช่น 1.28 -> ราคาไม่รวม VAT 1.20 -> 1.2840
        ใช้ตอนยกใบจาก o14 และตอนคิดใบร่างเก่าใหม่ ไม่แตะบรรทัดที่ไม่เข้าเงื่อนไข"""
        for line in self:
            if line.display_type or not line.price_unit or not line._npd_use_method_a():
                continue
            exact = round(round(line.price_unit / 1.07, 2) * 1.07, 4)
            if abs(exact - line.price_unit) > 0.00001:
                line.with_context(npd_skip_round=True).price_unit = exact

    def _npd_recalc_amounts(self):
        """คิดยอดใหม่ด้วยสูตรมาตรฐาน — ใช้ตอนสลับธง ก็อปใบ หรือยกใบจาก o14"""
        if not self:
            return
        self.invalidate_recordset(['price_subtotal', 'price_total', 'price_tax',
                                   'price_unit_no_vat'])
        self._compute_amount()
        self.order_id._compute_amounts()
