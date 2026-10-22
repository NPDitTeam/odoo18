# -*- coding: utf-8 -*-
"""ใบสั่งขายของ บริษัท เอ็นพีดี โลจิสติกส์ จำกัด ลงข้อมูลตรง ๆ แบบ o14 (NPD_Logistics_New)

o14 ฐาน Logistics ไม่ได้ติดตั้งสูตรงานเช่าของบริษัทอื่น แต่ o18 เป็นฐานเดียว สูตรเลยติดมาด้วย
ผู้ใช้สั่ง 22 ต.ค. 2569 ให้ปิด 3 อย่างเฉพาะ Logistics (บริษัทอื่นเหมือนเดิม):
  1. จำนวน = Quantity Rent × วันเช่า (pfb_npd_all_customs) — เคยทำให้ 364 กลายเป็น 10,920
  2. ค่าประกันดึงจากรายการราคาอัตโนมัติ (pfb_npd_all_customs)
  3. ราคารวม VAT ×1.07 แบบใบเช่า (npd_rent_price_round) — ใช้ราคาที่พิมพ์ตรง ๆ
  4. ภาษีรายบรรทัด — o14 ฐานโลจิสติกส์ใบสั่งขายไม่มีภาษีเลย (ตรวจ 60 วัน: สินค้าเช่า 4,059 / ค่าขนส่ง 157 บรรทัด)
"""
from odoo import api, models

from odoo.addons.transport_sync.models.sale_order import NPD_LOGISTICS_REGISTRY


def _is_logistics(line):
    company = line.company_id or line.order_id.company_id
    return bool(company) and company.company_registry == NPD_LOGISTICS_REGISTRY


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # 1) จำนวน × วัน ------------------------------------------------------
    @api.onchange('pfb_quantity', 'pfb_date_of_rent')
    def _onchange_rental_fields(self):
        if _is_logistics(self):
            return None
        return super()._onchange_rental_fields()

    @api.onchange('product_uom_qty')
    def _onchange_product_uom_qty_check_manual(self):
        if _is_logistics(self):
            return None
        return super()._onchange_product_uom_qty_check_manual()

    @api.depends('product_uom_qty', 'product_id', 'order_id.pfb_date_of_rent', 'pfb_quantity', 'is_manual_qty')
    def _compute_insurance_price(self):
        # จำค่าที่กรอกไว้ก่อน สูตรเดิมจะเขียนทับจำนวนด้วย Quantity Rent × วัน
        entered = {line: line.product_uom_qty for line in self if _is_logistics(line)}
        super()._compute_insurance_price()
        for line, qty in entered.items():
            if line.product_uom_qty != qty:
                line.product_uom_qty = qty
            # 2) ไม่มีค่าประกันในงานขนส่ง
            line.pfb_insurance_price = 0.0
            # 4) สูตรเดิมตั้งภาษีตามประเภทใบ ("ภาษีขายยังไม่ถึงกำหนด Vat 7%" กลุ่ม TAX 1%)
            #    o14 ฐานโลจิสติกส์ใบสั่งขายไม่มีภาษีทุกบรรทัด
            if line.tax_id:
                line.tax_id = False

    # 4) ภาษี: ใบสั่งขาย Logistics ไม่มีภาษี (ผู้ใช้สั่ง 22 ต.ค. 2569 "TAX 1% ไม่คิด") ----------
    @api.depends('product_id', 'company_id')
    def _compute_tax_id(self):
        others = self.filtered(lambda l: not _is_logistics(l))
        super(SaleOrderLine, others)._compute_tax_id()
        for line in self - others:
            line.tax_id = False

    @api.onchange('tax_id')
    def _onchange_tax_id_block(self):
        if _is_logistics(self):
            return None
        return super()._onchange_tax_id_block()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # สูตรเดิมเขียนจำนวนใหม่หลังสร้างบรรทัด → คืนค่าที่ผู้ใช้กรอก
        for line, vals in zip(lines, vals_list):
            if _is_logistics(line) and 'product_uom_qty' in vals \
                    and abs(line.product_uom_qty - (vals['product_uom_qty'] or 0.0)) > 0.0001:
                line.write({'product_uom_qty': vals['product_uom_qty'], 'is_manual_qty': True})
        return lines

    # 3) ราคารวม VAT แบบใบเช่า ----------------------------------------------
    def _npd_use_method_a(self):
        if _is_logistics(self):
            return False
        return super()._npd_use_method_a()
