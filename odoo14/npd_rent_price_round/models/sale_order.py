# -*- coding: utf-8 -*-
"""ธงวิธีคิดยอดระดับใบ — พอร์ตจากฝั่ง Odoo 14 ให้ยอดตรงกันทุกใบ"""
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    use_new_calc = fields.Boolean(
        string='คิดราคาต่อหน่วยแบบถอด Vat',
        default=True,
        copy=True,
        tracking=True,
        help='เปิด = ราคาต่อหน่วยที่เก็บไว้เป็นราคารวม VAT แต่คิดยอดแบบ '
             'ถอด VAT ก่อนแล้วบวก 7% กลับ (Method A) '
             'ปิด = ใช้สูตรมาตรฐานของ Odoo',
    )
    use_baan_kheaw = fields.Boolean(
        string='ใช้ราคาจากบ้านเขียว',
        default=False,
        copy=True,
        tracking=True,
        help='ติ๊ก = ไม่ใช้ Method A ใช้ราคาที่กรอกมาตรง ๆ',
    )
    vat_from_total = fields.Boolean(
        string='คำนวณ VAT จากยอดรวม',
        default=True,
        copy=True,
        tracking=True,
        help='เปิด (Method B) = ภาษี = ปัด(ยอดก่อนภาษี x 7%) ครั้งเดียวทั้งใบ '
             'ปิด = ภาษี = ผลรวมภาษีรายบรรทัดที่ปัดมาแล้ว',
    )
    can_edit_use_new_calc = fields.Boolean(
        compute='_compute_can_edit_use_new_calc')

    @api.depends_context('uid')
    def _compute_can_edit_use_new_calc(self):
        has_perm = self.env.user.can_edit_use_new_calc
        for rec in self:
            rec.can_edit_use_new_calc = has_perm

    @api.onchange('use_new_calc', 'use_baan_kheaw')
    def _onchange_npd_calc_flags(self):
        """รีเฟรชราคาถอด VAT ในฟอร์มทันทีที่สลับธง

        ห้ามใช้ line.update() เพราะฟอร์มจะส่งค่ากลับตอนบันทึกแล้วเข้า inverse
        เขียนทับ price_unit ทำให้ราคาเพี้ยนทีละนิดทุกครั้งที่สลับ
        """
        if not self.order_line:
            return
        self.order_line.invalidate_recordset(['price_unit_no_vat'])
        self.order_line._compute_price_unit_no_vat()

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        # ฝั่งใบแจ้งหนี้ยังไม่ได้พอร์ต ส่งค่าไปก่อนเพื่อไม่ให้ข้อมูลขาด
        # ถ้าวันหนึ่งพอร์ตมาแล้วจะใช้ได้ทันทีโดยไม่ต้องไล่แก้ใบเก่า
        for name in ('use_new_calc', 'use_baan_kheaw', 'vat_from_total'):
            if name in self.env['account.move']._fields:
                vals[name] = self[name]
        return vals

    def write(self, vals):
        res = super().write(vals)
        if {'use_new_calc', 'use_baan_kheaw', 'vat_from_total'} & set(vals):
            for order in self:
                order.order_line.with_context(
                    npd_skip_round=True)._npd_recalc_amounts()
        return res

    def copy(self, default=None):
        """กดซ้ำแล้วต้องบังคับคิดยอดใหม่

        ธงถูกก็อปมาพร้อมค่าเดิม (copy=True) จึงไม่นับว่า "เปลี่ยนค่า"
        hook ใน write เลยไม่ทำงาน แล้วยอดที่เขียนด้วย SQL ตอนสร้างบรรทัด
        จะถูกสูตรมาตรฐานของ Odoo เขียนทับกลับเป็นผลรวมรายบรรทัด
        """
        new_order = super().copy(default=default)
        if new_order.order_line:
            new_order.order_line.with_context(
                npd_skip_round=True)._npd_recalc_amounts()
        return new_order
