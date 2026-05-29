#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 ตรวจสอบว่า Booking BOOK-20251118-0027 ได้บันทึก delivery history หรือไม่
"""

import os
import sys
import django
from datetime import datetime, timedelta

# ตั้งค่า Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'odoo.settings')
sys.path.insert(0, r'C:\Program Files\Odoo 18.0.20251009\server')

# Odoo setup
import odoo
from odoo import api, fields, models
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

# Connect to Odoo database
db_name = 'Npd_Transport'
username = 'Npd_admin'
password = '1234'
server_url = 'http://localhost:8078'

print("=" * 70)
print("🔍 Checking Booking & Delivery History")
print("=" * 70)

try:
    # Login
    from xmlrpc import client as xmlrpc_client
    common = xmlrpc_client.ServerProxy(f'{server_url}/xmlrpc/2/common')
    
    uid = common.authenticate(db_name, username, password, {})
    if not uid:
        print("❌ Authentication failed!")
        sys.exit(1)
    
    print(f"✅ Authenticated as UID: {uid}")
    
    # Initialize models
    models = xmlrpc_client.ServerProxy(f'{server_url}/xmlrpc/2/object')
    
    # 1. ตรวจสอบ Booking BOOK-20251118-0027
    print("\n" + "=" * 70)
    print("1️⃣  Checking Booking BOOK-20251118-0027")
    print("=" * 70)
    
    booking_ids = models.execute_kw(
        db_name, uid, password,
        'vehicle.booking', 'search',
        [['name', '=', 'BOOK-20251118-0027']]
    )
    
    if booking_ids:
        booking = models.execute_kw(
            db_name, uid, password,
            'vehicle.booking', 'read',
            booking_ids,
            {'fields': ['id', 'name', 'state', 'driver_id', 'actual_pickup_time', 'actual_delivery_time', 'completion_date']}
        )[0]
        
        print(f"✅ Found booking: {booking['name']}")
        print(f"   ID: {booking['id']}")
        print(f"   State: {booking['state']}")
        print(f"   Driver: {booking['driver_id']}")
        print(f"   Pickup time: {booking['actual_pickup_time']}")
        print(f"   Delivery time: {booking['actual_delivery_time']}")
    else:
        print("❌ Booking not found!")
        sys.exit(1)
    
    # 2. ตรวจสอบ Delivery History ทั้งหมด
    print("\n" + "=" * 70)
    print("2️⃣  Checking ALL Delivery History Records")
    print("=" * 70)
    
    all_history_ids = models.execute_kw(
        db_name, uid, password,
        'delivery.history', 'search',
        [['driver_id', '=', booking['driver_id'][0]]],
        {'limit': 10, 'order': 'completion_date desc'}
    )
    
    print(f"📋 Found {len(all_history_ids)} delivery history records for driver {booking['driver_id'][0]}")
    
    if all_history_ids:
        histories = models.execute_kw(
            db_name, uid, password,
            'delivery.history', 'read',
            all_history_ids,
            {'fields': ['id', 'name', 'booking_id', 'driver_id', 'driver_name', 'completion_date', 'state']}
        )
        
        for i, hist in enumerate(histories):
            print(f"\n   📍 Record {i+1}:")
            print(f"      ID: {hist['id']}")
            print(f"      Name: {hist['name']}")
            print(f"      Booking: {hist['booking_id']}")
            print(f"      Driver: {hist['driver_name']}")
            print(f"      Completion: {hist['completion_date']}")
            print(f"      State: {hist['state']}")
    else:
        print("⚠️  No delivery history found!")
    
    # 3. ตรวจสอบเฉพาะ BOOK-20251118-0027
    print("\n" + "=" * 70)
    print("3️⃣  Checking History for BOOK-20251118-0027")
    print("=" * 70)
    
    specific_history = models.execute_kw(
        db_name, uid, password,
        'delivery.history', 'search',
        [['name', '=', 'BOOK-20251118-0027']]
    )
    
    if specific_history:
        hist = models.execute_kw(
            db_name, uid, password,
            'delivery.history', 'read',
            specific_history,
            {'fields': ['id', 'name', 'booking_id', 'partner_name', 'driver_name', 'completion_date', 'state']}
        )[0]
        
        print(f"✅ FOUND! Delivery history for BOOK-20251118-0027")
        print(f"   ID: {hist['id']}")
        print(f"   Booking: {hist['booking_id']}")
        print(f"   Partner: {hist['partner_name']}")
        print(f"   Driver: {hist['driver_name']}")
        print(f"   Completion: {hist['completion_date']}")
        print(f"   State: {hist['state']}")
    else:
        print("❌ NO delivery history found for BOOK-20251118-0027!")
        print("   👉 This means the booking.action_complete() did NOT create the history record")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
