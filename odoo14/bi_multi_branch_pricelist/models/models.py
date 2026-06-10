# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from datetime import datetime

# อัตราภาษีมูลค่าเพิ่ม (VAT) ที่ใช้ถอดออกจากราคา
VAT_RATE = 0.07
# ฐานข้อมูลที่ไม่มี VAT (ไม่ต้องถอด VAT) - อ้างอิงรูปแบบเดียวกับ pfb_npd_all_customs
NON_VAT_DBS = ('NPD_Intertrading_New_NonVat',)


class BiProductPricelist(models.Model):
    _inherit = "product.pricelist"

    pricelist_branch_id = fields.Many2one('res.branch', string='Branch')


class BiProductItemPricelist(models.Model):
    _inherit = "product.pricelist.item"

    branch_id = fields.Many2one('res.branch', string='Branch', readonly=True,
                                related='pricelist_id.pricelist_branch_id', store=True)

    # ราคาที่ถอด VAT ออกแล้ว = ราคา / (1 + อัตรา VAT)
    # store=True ทำให้คำนวณให้รายการราคาที่มีอยู่เดิมตอน upgrade module
    # และคำนวณอัตโนมัติเมื่อเพิ่มรายการราคาใหม่
    price_exclude_vat = fields.Float(
        string='ราคาถอด VAT', digits='Product Price',
        compute='_compute_price_exclude_vat', store=True, readonly=True,
        help='ราคาที่ถอดภาษีมูลค่าเพิ่ม (VAT) ออกแล้ว = ราคา / (1 + อัตรา VAT)')

    def _get_vat_rate(self):
        """อัตรา VAT ที่ใช้ถอด; คืนค่า 0 สำหรับฐานข้อมูลที่ไม่มี VAT"""
        if self.env.cr.dbname in NON_VAT_DBS:
            return 0.0
        return VAT_RATE

    @api.depends('fixed_price', 'compute_price')
    def _compute_price_exclude_vat(self):
        for item in self:
            rate = item._get_vat_rate()
            if item.compute_price == 'fixed':
                item.price_exclude_vat = item.fixed_price / (1.0 + rate)
            else:
                item.price_exclude_vat = 0.0


class BiSaleOrderLinePricelist(models.Model):
    _inherit = "sale.order.line"

    def _get_pricelist_price(self):
        """ราคาต่อหน่วย (price_unit) ที่ดึงจากรายการราคาให้ใช้ราคาถอด VAT แทนราคาเดิม

        เดิม price_unit ใช้ราคาจากกฎรายการราคา (fixed_price) ตรง ๆ
        ปรับให้ถอด VAT ออกก่อน โดยหารด้วย (1 + อัตรา VAT) ซึ่งเท่ากับค่า
        ในฟิลด์ price_exclude_vat (ทำในรูปสกุลเงินของออเดอร์เพื่อรองรับการแปลงสกุลเงิน)
        """
        price = super()._get_pricelist_price()
        item = self.pricelist_item_id
        if item and item.compute_price == 'fixed':
            rate = item._get_vat_rate()
            if rate:
                price = price / (1.0 + rate)
        return price
