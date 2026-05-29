#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Fix Foreign Key Violation in vehicle_tracking
ลบหรือ update driver_id ที่ไม่มีจริงในตาราง vehicle_driver
"""

import os
import sys

# Add Odoo path
odoo_path = r"C:\Program Files\Odoo 18.0.20251009\server"
sys.path.insert(0, odoo_path)

import odoo
from odoo import api, fields, models
from odoo.tools import sql

def fix_tracking_foreign_keys():
    """แก้ไข Foreign Key Violation"""
    
    # เชื่อมต่อ Odoo
    odoo.cli.main(['--db-filter=Npd_Transport', '--stop-after-init', '-d', 'Npd_Transport'])
    
    print("=" * 60)
    print("🔧 Fixing vehicle_tracking Foreign Keys")
    print("=" * 60)
    print()

if __name__ == '__main__':
    fix_tracking_foreign_keys()
