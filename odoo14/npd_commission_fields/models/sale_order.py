# -*- coding: utf-8 -*-
"""ส่งเซลล์ผู้ติดต่อจากใบสั่งขายไปยังใบแจ้งหนี้

ค่าคอม Sales คิดจากใบแจ้งหนี้ ไม่ใช่ใบสั่งขาย ถ้าใบแจ้งหนี้ไม่มีชื่อเซลล์ติดไป
รายงานจะจัดกลุ่มไม่ได้และยอดของเซลล์ทุกคนจะเป็นศูนย์
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)
        for invoice in invoices:
            orders = invoice.line_ids.mapped('sale_line_ids.order_id')
            if not orders:
                continue
            # ใบแจ้งหนี้รวมหลายใบสั่งขายได้ ใช้ใบแรกเป็นตัวแทนเหมือน Odoo 14
            order = orders[0]
            vals = {}
            if order.sales_contact and not invoice.sales_contact_id:
                vals['sales_contact_id'] = order.sales_contact.id
            if getattr(order, 'contact_type', False) and not invoice.contact_type:
                vals['contact_type'] = order.contact_type
            # วันที่เริ่มต้น/สิ้นสุดการเช่า จากใบสั่งขาย (ฟิลด์มาจากโมดูลอื่น เช็กก่อนว่ามี)
            for src, dst in (('start_rent_date', 'start_date'), ('end_rent_date', 'end_date')):
                if (src in order._fields and dst in invoice._fields
                        and order[src] and not invoice[dst]):
                    vals[dst] = order[src]
            if not invoice.reason_code_id:
                rent_code = invoice._npd_default_reason_code()
                if rent_code:
                    vals['reason_code_id'] = rent_code.id
            if vals:
                invoice.write(vals)
                if len(orders) > 1:
                    _logger.info(
                        '[COMMISSION] ใบแจ้งหนี้ %s รวม %d ใบสั่งขาย '
                        'ใช้เซลล์จากใบแรก (%s)',
                        invoice.name, len(orders), order.name)
        return invoices
