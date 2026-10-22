# -*- coding: utf-8 -*-
"""ค่าเริ่มต้นของช่องบังคับที่ซ่อนในใบสั่งขายของ บริษัท เอ็นพีดี โลจิสติกส์ จำกัด

ช่องพวกนี้บังคับในฐานข้อมูล (NOT NULL) ซ่อนแล้วต้องเติมค่าให้ ไม่งั้นบันทึกไม่ได้
- การติดต่อของลูกค้า: o14 ฐานโลจิสติกส์เป็น "สาขา" ทุกใบ (90 วัน 1,682 ใบ)
- ช่องทางลูกค้า (แท็บการตลาด): o14 ฐานโลจิสติกส์ไม่มีช่องนี้
  ดึงข้อมูลการเช่ามา = ใช้ของใบต้นทาง · ไม่มี = "พนักงานสาขาติดต่อ"
"""
from odoo import api, models

from odoo.addons.transport_sync.models.sale_order import NPD_LOGISTICS_REGISTRY

DEFAULT_CHANNEL_NAME = 'พนักงานสาขาติดต่อ'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _npd_logistics_default_channel(self):
        Channel = self.env['customer.channel'].sudo()
        return (Channel.search([('name', '=', DEFAULT_CHANNEL_NAME)], limit=1)
                or Channel.search([('name', 'ilike', 'พนักงานสาขา')], limit=1)
                or Channel.search([], limit=1))

    def _npd_logistics_fill_required(self, vals, company):
        if not company or company.company_registry != NPD_LOGISTICS_REGISTRY:
            return vals
        if not vals.get('contact_type'):
            vals['contact_type'] = 'branch'
        if 'customer_channel_id' in self._fields and not vals.get('customer_channel_id'):
            vals['customer_channel_id'] = self._npd_logistics_default_channel().id
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        Company = self.env['res.company']
        for vals in vals_list:
            company = Company.browse(vals['company_id']) if vals.get('company_id') else self.env.company
            self._npd_logistics_fill_required(vals, company)
        return super().create(vals_list)

    def _fetch_rental_data(self, source_company, so_number):
        res = super()._fetch_rental_data(source_company, so_number)
        if self.company_id.company_registry == NPD_LOGISTICS_REGISTRY and 'customer_channel_id' in self._fields:
            source = self.env['sale.order'].sudo().search(
                [('name', '=', so_number), ('company_id', '=', source_company.id)], limit=1)
            if source.customer_channel_id and source.customer_channel_id != self.customer_channel_id:
                self.customer_channel_id = source.customer_channel_id
        return res
