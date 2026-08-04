# -*- coding: utf-8 -*-
from odoo import api, fields, models

# จำนวนเลขอ้างอิงขั้นต่ำใน deposit_ref ที่ถือว่าเอกสารนี้เป็น "บิลต่ออายุ"
# เอกสารที่ถูกกดซ้ำครั้งแรกจะมีเลขอ้างอิง 1 ค่า (ดู sale.order.copy_data ใน
# pfb_npd_add_date_quatation_order) จึงใช้ค่า 1
RENEWAL_MIN_REF_COUNT = 1


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    renewal_bill_status = fields.Selection(
        [('renew', 'ต่ออายุบิล')],
        string='สถานะต่ออายุบิล',
        compute='_compute_renewal_bill_status',
        store=True,
        help='คำนวณจาก "เลขอ้างอิงเงินประกัน": ถ้ามีเลขอ้างอิง = ต่ออายุบิล, ถ้าไม่มี = ว่าง',
    )

    @api.depends('deposit_ref')
    def _compute_renewal_bill_status(self):
        for order in self:
            refs = [r.strip() for r in (order.deposit_ref or '').split(',') if r.strip()]
            order.renewal_bill_status = 'renew' if len(refs) >= RENEWAL_MIN_REF_COUNT else False
