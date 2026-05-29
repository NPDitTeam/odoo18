import os
import sys

# สร้างการเชื่อมต่อผ่าน xmlrpc
from xmlrpc import client as xmlrpc_client

db_name = 'Npd_Transport'
username = 'Npd_admin'
password = '1234'
server_url = 'http://localhost:8078'

print("=" * 70)
print("🔍 Checking Booking & Delivery History")
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
            {'fields': ['id', 'name', 'state', 'driver_id', 'actual_pickup_time', 'actual_delivery_time']}
        )[0]
        
        print(f"✅ Found booking: {booking['name']}")
        print(f"   ID: {booking['id']}")
        print(f"   State: {booking['state']}")
        print(f"   Driver: {booking['driver_id']}")
        print(f"   Pickup time: {booking['actual_pickup_time']}")
        print(f"   Delivery time: {booking['actual_delivery_time']}")
    else:
        print("❌ Booking BOOK-20251118-0027 not found!")
        sys.exit(1)
    
    # 2. ตรวจสอบ Delivery History เฉพาะ BOOK-20251118-0027
    print("\n" + "=" * 70)
    print("2️⃣  Checking History for BOOK-20251118-0027")
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
        
        print(f"✅ FOUND! Delivery history exists!")
        print(f"   ID: {hist['id']}")
        print(f"   Name: {hist['name']}")
        print(f"   Booking: {hist['booking_id']}")
        print(f"   Partner: {hist['partner_name']}")
        print(f"   Driver: {hist['driver_name']}")
        print(f"   Completion: {hist['completion_date']}")
        print(f"   State: {hist['state']}")
    else:
        print("❌ NO delivery history found for BOOK-20251118-0027!")
        print("   ⚠️  The booking.action_complete() did NOT create the history record")
        print("   📍 Checking driver's booking state...")
        
        # ตรวจสอบจำนวน record ทั้งหมด
        all_history_ids = models.execute_kw(
            db_name, uid, password,
            'delivery.history', 'search',
            []
        )
        print(f"   Total delivery.history records in DB: {len(all_history_ids)}")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
