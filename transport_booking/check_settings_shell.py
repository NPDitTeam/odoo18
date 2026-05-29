#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตรวจสอบ tracking_interval ผ่าน Odoo shell
รันด้วย: odoo-bin shell -c odoo.conf -d odoo18
"""

import sys
import os

print("=" * 70)
print(" ตรวจสอบค่า tracking_interval ใน Odoo")
print("=" * 70)
print()

try:
    # Import Odoo (จะทำงานเมื่อรันใน Odoo shell)
    from odoo import api, SUPERUSER_ID
    
    # Get registry
    import odoo
    registry = odoo.registry(os.environ.get('ODOO_DATABASE', 'odoo18'))
    
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        # ค้นหา tracking.settings
        TrackingSettings = env['tracking.settings']
        settings = TrackingSettings.search([])
        
        print(f"📊 พบ tracking.settings ทั้งหมด: {len(settings)} รายการ")
        print("-" * 70)
        
        if settings:
            for setting in settings:
                print(f"\n🔹 Setting ID: {setting.id}")
                print(f"   👤 User: {setting.user_id.name} ({setting.user_id.login})")
                print(f"   ⏱️  tracking_interval: {setting.tracking_interval} นาที")
                print(f"   ✅ tracking_enabled: {setting.tracking_enabled}")
                print(f"   🗺️  show_route: {setting.show_route}")
                print(f"   🚗 show_speed: {setting.show_speed}")
                print(f"   🗺️  map_type: {setting.map_type}")
                print("-" * 70)
        else:
            print("⚠️  ไม่พบข้อมูล tracking.settings")
            print()
            print("วิธีแก้:")
            print("1. Login เข้า Odoo")
            print("2. ไปที่เมนู Settings หรือที่คุณสร้างไว้")
            print("3. ตั้งค่า tracking_interval")
            print("4. Save")
        
        print()
        print("=" * 70)
        print(" เสร็จสิ้น!")
        print("=" * 70)
        
except ImportError:
    print("❌ ไม่สามารถ import Odoo ได้")
    print()
    print("วิธีรัน script นี้:")
    print("=" * 70)
    print()
    print("cd \"C:\\Program Files\\Odoo 18.0.20251009\\server\"")
    print("python odoo-bin shell -c odoo.conf -d odoo18 --no-http")
    print()
    print("จากนั้นใน Python shell พิมพ์:")
    print()
    print(">>> env['tracking.settings'].search([])")
    print(">>> for s in env['tracking.settings'].search([]):")
    print("...     print(f'{s.user_id.name}: {s.tracking_interval} minutes')")
    print()
    print("=" * 70)
