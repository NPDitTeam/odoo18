# -*- coding: utf-8 -*-
"""Hook หลังติดตั้ง transport_booking

หมายเหตุการอัปเกรดมา Odoo 18: ลายเซ็น hook เปลี่ยนจาก (cr, registry) เป็น (env)
ตั้งแต่ Odoo 17 — ของเดิมทำให้ติดตั้งโมดูลนี้บน Odoo 18 ไม่ผ่าน
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """เพิ่มคอลัมน์สำหรับลายน้ำ GPS บนภาพหลักฐานการส่ง

    ใช้ ADD COLUMN IF NOT EXISTS จึงรันซ้ำได้ปลอดภัย
    """
    _logger.info('[TRANSPORT_BOOKING] เริ่มสร้างฟิลด์ลายน้ำ GPS')
    columns = [
        ('delivery_timestamp', 'timestamp without time zone'),
        ('delivery_latitude', 'numeric(10,7)'),
        ('delivery_longitude', 'numeric(10,7)'),
    ]
    for name, column_type in columns:
        env.cr.execute(
            'ALTER TABLE vehicle_booking ADD COLUMN IF NOT EXISTS %s %s'
            % (name, column_type))
        _logger.info('[TRANSPORT_BOOKING] ✓ คอลัมน์ %s พร้อมใช้งาน', name)
    _logger.info('[TRANSPORT_BOOKING] สร้างฟิลด์ลายน้ำ GPS เสร็จ')
