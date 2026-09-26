# -*- coding: utf-8 -*-
"""คิดยอดรายบรรทัดแบบฝั่ง Odoo 14

ตัวเลขสองฝั่งต้องเท่ากันถึงหลักสตางค์ จึงลอกลำดับการปัดเศษมาทั้งดุ้น
ห้ามย่อหรือสลับลำดับ round() เพราะผลจะต่างกันทีละสตางค์แล้วสะสมทั้งใบ
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
        if not order or not order.use_new_calc or order.use_baan_kheaw:
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
            return round(self.price_unit_no_vat * 1.07, 2)
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
    def _npd_compute_method_a(self):
        """ยอดรายบรรทัดแบบ Method A → {line_id: (ก่อนภาษี, รวม, ภาษี)}

        คิด VAT ไปข้างหน้าจากยอดก่อนภาษีที่แสดงจริง ไม่ใช่ถอดย้อนจากราคา
        รวม VAT ที่ปัด 2 ตำแหน่งมาแล้ว (การปัด 0.10 เป็น 0.11 ทำให้ภาษีบวม)
        บรรทัดราคา 0 (ของแถม) ข้ามไป เพราะไม่มีอะไรให้ถอด
        """
        result = {}
        for line in self:
            if not line._npd_use_method_a():
                continue
            if not line.price_unit or not line.product_uom_qty:
                continue
            unit_ex_vat = round(line.price_unit / 1.07, 2)
            new_subtotal = round(unit_ex_vat * line.product_uom_qty, 2)
            new_tax = round(new_subtotal * VAT_RATE, 2)
            result[line.id] = (new_subtotal,
                               round(new_subtotal + new_tax, 2),
                               new_tax)
        return result

    def _npd_write_order_totals(self, order_ids):
        """รวมยอดจากบรรทัดแล้วเขียนลงหัวใบด้วย SQL

        ต้องเขียนด้วย SQL เพราะ amount_* เป็นฟิลด์คำนวณ ถ้าเขียนผ่าน ORM
        สูตรมาตรฐานของ Odoo จะคำนวณทับกลับเป็นผลรวมรายบรรทัดทันที
        """
        if not order_ids:
            return
        cr = self.env.cr
        Order = self.env['sale.order']
        for order_id in order_ids:
            cr.execute("""
                select coalesce(sum(price_subtotal), 0),
                       coalesce(sum(price_tax), 0)
                  from sale_order_line where order_id = %s
            """, (order_id,))
            untaxed, tax = cr.fetchone()
            untaxed = round(float(untaxed or 0), 2)
            tax = round(float(tax or 0), 2)
            if Order.browse(order_id).vat_from_total:
                # Method B — ปัดครั้งเดียวทั้งใบ ยอมให้ต่างจากผลบวกรายบรรทัด
                tax = round(untaxed * VAT_RATE, 2)
            cr.execute("""
                update sale_order
                   set amount_untaxed = %s, amount_tax = %s, amount_total = %s
                 where id = %s
            """, (untaxed, tax, round(untaxed + tax, 2), order_id))

    def _npd_force_round_sql(self):
        rounded = self._npd_compute_method_a()
        cr = self.env.cr
        for line_id, (subtotal, total, tax) in rounded.items():
            cr.execute("""
                update sale_order_line
                   set price_subtotal = %s, price_total = %s, price_tax = %s
                 where id = %s
            """, (subtotal, total, tax, line_id))
        # ใบที่ติ๊กใช้ราคาบ้านเขียวไม่ผ่าน Method A แต่ยังต้องคิด Method B
        # จึงต้องรวมเข้ามาด้วย ไม่งั้นยอดภาษีของใบพวกนั้นค้างเป็นแบบเก่า
        order_ids = sorted(set(self.mapped('order_id').ids))
        if order_ids:
            self.env.flush_all()
            self._npd_write_order_totals(order_ids)
            self.env.invalidate_all()

    def _npd_recalc_amounts(self):
        """สั่งคิดยอดใหม่ทั้งใบ — ใช้ตอนธงเปลี่ยนหรือหลังก็อปใบ"""
        if not self:
            return
        self.invalidate_recordset(['price_subtotal', 'price_total', 'price_tax',
                                   'use_new_calc', 'use_baan_kheaw',
                                   'vat_from_total'])
        self._compute_amount()
        # ต้องบังคับให้ค่าใหม่ลงฐานก่อน ไม่งั้น SQL ด้านล่างจะไปรวมค่าเก่า
        self.flush_recordset()
        self._npd_force_round_sql()

    # ------------------------------------------------------------------
    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id',
                 'use_new_calc', 'use_baan_kheaw')
    def _compute_amount(self):
        res = super()._compute_amount()
        rounded = self._npd_compute_method_a()
        for line in self:
            if line.id in rounded:
                subtotal, total, tax = rounded[line.id]
                line.price_subtotal = subtotal
                line.price_total = total
                line.price_tax = tax
        return res

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._npd_force_round_sql()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('npd_skip_round'):
            self.with_context(npd_skip_round=True)._npd_force_round_sql()
        return res
