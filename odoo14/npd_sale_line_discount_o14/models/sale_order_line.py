# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    discount_method = fields.Selection(
        [('fix', 'Fixed'), ('per', 'Percentage')], string='ประเภทการลดราคา')
    # ชื่อเดียวกับ bi_sale_purchase_discount_with_tax ของ o14 — sale_isolated_quotation ใช้เป็นฐานเกณฑ์ 50%
    # = ยอดบรรทัดก่อนหักส่วนลด ไม่รวม VAT (o14 ตั้งป้ายว่า "ยอดหลังหักส่วนลด" แต่ค่าจริงคือยอดก่อนหัก)
    price_subtotal_without_discount = fields.Monetary(
        string='ยอดก่อนหักส่วนลด', compute='_compute_price_subtotal_without_discount')
    commitment_date = fields.Datetime(
        related='order_id.commitment_date', string='วันที่จัดส่งสินค้า')

    def _npd_gross_untaxed(self):
        """ยอดบรรทัดก่อนหักส่วนลด ไม่รวม VAT (ราคาต่อหน่วยของบริษัทเช่าเป็นแบบรวม VAT)"""
        self.ensure_one()
        if not self.product_id or self.display_type:
            return 0.0
        taxes = self.tax_id.compute_all(
            self.price_unit, self.order_id.currency_id, self.product_uom_qty,
            product=self.product_id, partner=self.order_id.partner_shipping_id)
        return taxes['total_excluded']

    def _npd_discount_baht(self):
        """ส่วนลดเป็นบาท (ไม่รวม VAT): Fixed = ยอดที่กรอก, Percentage = % ของยอดก่อนหัก"""
        self.ensure_one()
        if not self.discount_amount:
            return 0.0
        if self.discount_method == 'per':
            return self._npd_gross_untaxed() * self.discount_amount / 100.0
        return self.discount_amount

    @api.depends('price_unit', 'product_uom_qty', 'tax_id')
    def _compute_price_subtotal_without_discount(self):
        for line in self:
            line.price_subtotal_without_discount = line._npd_gross_untaxed()

    # ส่วนลดหักยอดจริงผ่านช่อง "ลด%" มาตรฐาน → ใบสั่งขาย/VAT/ใบแจ้งหนี้คิดให้เองแบบ Odoo (ผู้ใช้สั่ง 23 ต.ค. 2569)
    # Fixed หักจากยอดไม่รวม VAT แบบ o14 (price_subtotal = stwd - discount_amount) จึงแปลงเป็น % ของยอดนั้น
    @api.depends('product_id', 'product_uom', 'product_uom_qty', 'discount_type_selection',
                 'discount_method', 'discount_amount', 'price_unit', 'tax_id')
    def _compute_discount(self):
        super()._compute_discount()
        for line in self:
            if line.discount_method not in ('fix', 'per') or not line.product_id or line.display_type:
                continue
            # ส่วนลดค่าเช่า (rental) หักตอนคืนเงินประกัน (account_voucher_npd) อยู่แล้ว หักที่บรรทัดอีกจะซ้ำ
            if line.discount_type_selection == 'rental':
                continue
            if not line.discount_amount:
                line.discount = 0.0
            elif line.discount_method == 'per':
                line.discount = min(line.discount_amount, 100.0)
            else:
                gross = line._npd_gross_untaxed()
                line.discount = min(line.discount_amount / gross * 100.0, 100.0) if gross else 0.0

    @api.constrains('discount_method', 'discount_amount')
    def _check_npd_discount_percent(self):
        # SO-261023-0026: เลือก Percentage แต่กรอกยอดบาท 1,207.44 → จะกลายเป็นลด 100%
        for line in self:
            if line.discount_method == 'per' and not 0 <= line.discount_amount <= 100:
                raise ValidationError(_(
                    '%s: ประเภทการลดราคาแบบ Percentage กรอกได้ 0–100 (%%) เท่านั้น\n'
                    'ถ้าจะลดเป็นจำนวนเงิน ให้เลือก Fixed') % line.product_id.display_name)

    @api.onchange('discount_amount', 'discount_type_selection', 'discount_method')
    def _onchange_npd_discount_limit(self):
        # แทน _onchange_discount_amount ของ pfb_npd_all_customs (ไม่มี decorator + ข้อความติด %%)
        for line in self:
            if line.discount_amount and line.discount_type_selection == 'product':
                max_discount = line.price_subtotal_without_discount * 0.5
                if max_discount and line._npd_discount_baht() > max_discount:
                    return {'warning': {
                        'title': _('ส่วนลดเกินเกณฑ์'),
                        'message': _('ส่วนลดเกิน 50%% ของยอดรายการ (สูงสุด %s)\n'
                                     'ต้องกด "Send for Approval" ให้ผู้อนุมัติก่อน Convert to Order')
                        % '{:,.2f}'.format(max_discount),
                    }}
