#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 สร้าง delivery_history สำหรับ BOOK-20251118-0027 แบบ manual
"""
import os
import sys

# ใช้ xmlrpc เพื่อสร้างทดสอบ
from xmlrpc import client as xmlrpc_client

db_name = 'Npd_Transport'
username = 'Npd_admin'
password = '1234'
server_url = 'http://localhost:8078'

print("=" * 70)
print("🔧 Creating delivery_history manually for BOOK-20251118-0027")
print("=" * 70)

try:
    # Login
    common = xmlrpc_client.ServerProxy(f'{server_url}/xmlrpc/2/common')
    uid = common.authenticate(db_name, username, password, {})
    
    if not uid:
        print("❌ Authentication failed!")
        sys.exit(1)
    
    print(f"✅ Authenticated as UID: {uid}")
    
    # Initialize models
    models = xmlrpc_client.ServerProxy(f'{server_url}/xmlrpc/2/object')
    
    # ดึงข้อมูล booking
    print("\n📋 Fetching booking BOOK-20251118-0027...")
    booking_ids = models.execute_kw(
        db_name, uid, password,
        'vehicle.booking', 'search',
        [['name', '=', 'BOOK-20251118-0027']]
    )
    
    if not booking_ids:
        print("❌ Booking not found!")
        sys.exit(1)
    
    booking_id = booking_ids[0]
    booking = models.execute_kw(
        db_name, uid, password,
        'vehicle.booking', 'read',
        [booking_id],
        {'fields': [
            'id', 'name', 'partner_id', 'driver_id', 'vehicle_id',
            'pickup_location', 'destination', 'distance_km', 'total_weight_order',
            'shipping_cost', 'actual_pickup_time', 'actual_delivery_time',
            'pickup_photo', 'delivery_photo', 'receiver_name', 'receiver_signature',
            'note', 'tracking_notes'
        ]}
    )[0]
    
    print(f"✅ Found booking: {booking['name']}")
    print(f"   ID: {booking['id']}")
    print(f"   Driver: {booking['driver_id']}")
    print(f"   Partner: {booking['partner_id']}")
    
    # สร้าง delivery_history
    print("\n📝 Creating delivery_history...")
    
    history_vals = {
        'name': booking['name'],
        'booking_id': booking['id'],
        'partner_id': booking['partner_id'][0] if booking['partner_id'] else False,
        'partner_name': booking['partner_id'][1] if booking['partner_id'] else '',
        'pickup_location': booking['pickup_location'],
        'destination': booking['destination'],
        'distance_km': booking['distance_km'],
        'total_weight_order': booking['total_weight_order'],
        'driver_id': booking['driver_id'][0] if booking['driver_id'] else False,
        'driver_name': booking['driver_id'][1] if booking['driver_id'] else '',
        'vehicle_id': booking['vehicle_id'][0] if booking['vehicle_id'] else False,
        'vehicle_name': booking['vehicle_id'][1] if booking['vehicle_id'] else '',
        'shipping_cost': booking['shipping_cost'],
        'actual_pickup_time': booking['actual_pickup_time'],
        'actual_delivery_time': booking['actual_delivery_time'],
        'completion_date': booking['actual_delivery_time'],
        'pickup_photo': booking['pickup_photo'],
        'delivery_photo': booking['delivery_photo'],
        'receiver_name': booking['receiver_name'],
        'receiver_signature': booking['receiver_signature'],
        'note': booking['note'],
        'tracking_notes': booking['tracking_notes'],
        'state': 'completed',
    }
    
    print(f"📦 Data to save:")
    for k, v in history_vals.items():
        if isinstance(v, bytes):
            print(f"   {k}: <binary data>")
        else:
            print(f"   {k}: {v}")
    
    # สร้าง record
    history_id = models.execute_kw(
        db_name, uid, password,
        'delivery.history', 'create',
        [history_vals]
    )
    
    print(f"\n✅ SUCCESS! Created delivery_history with ID: {history_id}")
    
    # ตรวจสอบว่าถูกสร้างหรือไม่
    print("\n✅ Verifying...")
    history = models.execute_kw(
        db_name, uid, password,
        'delivery.history', 'read',
        [history_id],
        {'fields': ['id', 'name', 'booking_id', 'driver_name', 'completion_date', 'state']}
    )[0]
    
    print(f"   ID: {history['id']}")
    print(f"   Name: {history['name']}")
    print(f"   Driver: {history['driver_name']}")
    print(f"   Completion: {history['completion_date']}")
    print(f"   State: {history['state']}")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
