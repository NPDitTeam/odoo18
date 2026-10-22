# -*- coding: utf-8 -*-
"""ดึงจำนวนสินค้าจาก Odoo 14 ใหม่ เฉพาะบรรทัดที่จำนวนเป็น 0

ใช้ตอนเลือกคำสั่งขนส่งในหน้าจองคิวรถ (ผู้ใช้สั่ง 22 ต.ค. 2569) — เดิมใบประเภท "ขาย" ซิงก์มาได้ 0
เพราะ o14 ส่ง Quantity Rent ซึ่งใบขายล็อกเป็น 0 ไว้ (แก้ฝั่ง o14 แล้ว แต่ใบที่ซิงก์มาก่อนยังค้าง)

ไม่ใช้ _process_order_lines ของรอบซิงก์ปกติ เพราะตัวนั้นล้างผลตรวจนับเมื่อจำนวนเปลี่ยน
ที่นี่แตะแค่ quantity ของบรรทัดที่เป็น 0 และยังไม่ได้ตรวจ
"""
import logging

import requests

from odoo import models

from .transport_order import ODOO14_CONFIG

_logger = logging.getLogger(__name__)

# บรรทัดค่าบริการ (ค่าขนส่ง ค่าบริการ ...) ไม่ใช่ของที่ต้องนับ
SERVICE_PREFIX = 'ค่า'


class TransportOrderQtyRefresh(models.Model):
    _inherit = 'transport.order'

    def _npd_zero_qty_goods(self):
        self.ensure_one()
        # บรรทัดไม่มีสินค้า = หัวข้อ/หมายเหตุใน SO ไม่ใช่ของ
        return self.order_line_ids.filtered(
            lambda l: not l.quantity and (l.product_name_o14 or l.product_id)
            and not (l.product_name_o14 or '').startswith(SERVICE_PREFIX))

    def _npd_fetch_o14_lines(self):
        """{o14 line id: quantity} ของใบนี้จาก o14 (None = ติดต่อ o14 ไม่ได้)"""
        self.ensure_one()
        try:
            session = requests.Session()
            auth = session.post(f"{ODOO14_CONFIG['url']}/web/session/authenticate", json={
                'jsonrpc': '2.0',
                'params': {
                    'db': ODOO14_CONFIG['database'],
                    'login': ODOO14_CONFIG['username'],
                    'password': ODOO14_CONFIG['password'],
                },
            }, timeout=10, verify=False).json()
            if not (auth.get('result') or {}).get('uid'):
                return None
            res = session.post(f"{ODOO14_CONFIG['url']}/api/sale_order/{self.odoo14_id}",
                               json={'jsonrpc': '2.0', 'params': {}}, timeout=15, verify=False).json()
        except Exception as e:  # เครือข่าย/o14 ล่ม ไม่ให้หน้าจองพัง
            _logger.warning('ดึงจำนวนสินค้า o14 ใบ %s ไม่สำเร็จ: %s', self.name, e)
            return None
        data = (res.get('result') or {}).get('data') or {}
        return {line['id']: line.get('quantity') or 0.0 for line in data.get('order_lines') or []}

    def npd_refresh_zero_qty_from_o14(self):
        """คืน (จำนวนบรรทัดที่แก้ได้, บรรทัดที่ยังเป็น 0, ติดต่อ o14 ได้ไหม)"""
        self.ensure_one()
        zero = self._npd_zero_qty_goods().filtered(lambda l: (l.check_state or 'pending') == 'pending')
        if not zero:
            return 0, self._npd_zero_qty_goods(), True
        if not self.odoo14_id:
            return 0, zero, True
        o14 = self._npd_fetch_o14_lines()
        if o14 is None:
            return 0, zero, False
        fixed = 0
        for line in zero:
            qty = o14.get(line.odoo14_id) or 0.0
            if qty > 0:
                line.sudo().write({'quantity': qty})
                fixed += 1
        if fixed:
            _logger.info('ดึงจำนวนสินค้าจาก o14 ใหม่ ใบ %s: %s บรรทัด', self.name, fixed)
        return fixed, self._npd_zero_qty_goods(), True
