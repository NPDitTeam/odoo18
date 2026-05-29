#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script สำหรับสร้าง delivery.history records จากการจองที่มีอยู่แล้ว
เพื่อทดสอบ Flutter app ที่ดึงประวัติการจัดส่ง
"""

import os
import sys
import django

# ตั้งค่า Odoo environment
os.environ['DJANGO_SETTINGS_MODULE'] = 'odoo.settings'
sys.path.insert(0, r'C:\Program Files\Odoo 18.0.20251009\server')

# Import Odoo
import odoo
from odoo import api, fields
from odoo.cli import main

# ใช้ odoo.py เพื่อ run script
if __name__ == '__main__':
    # ใช้ Odoo shell แทน
    print("""
    ให้รัน command นี้ใน Odoo Shell:
    
    cd "C:\\Program Files\\Odoo 18.0.20251009\\server"
    python bin/odoo shell -d NPD_Logistics_demo
    
    แล้วพิมพ์:
    
    # ค้นหา booking ที่ status = 'confirmed'
    bookings = env['vehicle.booking'].search([('state', '=', 'confirmed')])
    
    # สำหรับแต่ละ booking ให้เรียก action_done()
    for booking in bookings[:1]:  # ทดสอบแค่ 1 รายการ
        booking.action_done()
        print(f"✅ Marked as done: {booking.name}")
    """)
