# -*- coding: utf-8 -*-
"""
สคริปต์สำหรับ Geocode bookings ที่มี destination แต่ยังไม่มีพิกัด
รัน: python geocode_existing_bookings.py
"""

import xmlrpc.client
import sys

# Odoo Configuration
ODOO_URL = 'http://localhost:8078'
ODOO_DB = 'Npd_Transport'
ODOO_USERNAME = 'Npd_admin'
ODOO_PASSWORD = '1234'

def main():
    try:
        print("="*60)
        print("🌍 Geocoding Existing Bookings")
        print("="*60)
        
        # 1. เชื่อมต่อ Odoo
        print("\n📡 Connecting to Odoo...")
        common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
        uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
        
        if not uid:
            print("❌ Authentication failed!")
            sys.exit(1)
        
        print(f"✅ Connected as user ID: {uid}")
        
        # 2. เชื่อมต่อกับ object endpoint
        models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
        
        # 3. ค้นหา bookings ที่ยังไม่มีพิกัด
        print("\n🔍 Searching for bookings without coordinates...")
        booking_ids = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'vehicle.booking', 'search',
            [[
                '|',
                ['destination_latitude', '=', False],
                ['destination_latitude', '=', 0.0],
                ['destination', '!=', False]
            ]]
        )
        
        print(f"📋 Found {len(booking_ids)} bookings without coordinates")
        
        if not booking_ids:
            print("✅ All bookings already have coordinates!")
            return
        
        # 4. อ่านข้อมูล bookings
        bookings = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'vehicle.booking', 'read',
            [booking_ids, ['id', 'name', 'destination', 'destination_latitude', 'destination_longitude']]
        )
        
        # 5. Geocode แต่ละ booking
        print("\n🗺️  Starting geocoding process...")
        success_count = 0
        fail_count = 0
        
        for booking in bookings:
            booking_id = booking['id']
            booking_name = booking['name']
            destination = booking['destination']
            
            print(f"\n{'='*60}")
            print(f"📍 Processing: {booking_name}")
            print(f"   Destination: {destination}")
            
            try:
                # Force geocoding โดยส่ง destination พร้อมกับ reset พิกัดเป็น False
                # ทำให้ write() method ทำการ geocode ใหม่
                result = models.execute_kw(
                    ODOO_DB, uid, ODOO_PASSWORD,
                    'vehicle.booking', 'write',
                    [[booking_id], {
                        'destination': destination,
                        'destination_latitude': False,  # Force geocode
                        'destination_longitude': False,
                    }]
                )
                
                if result:
                    # อ่านพิกัดที่ได้
                    updated = models.execute_kw(
                        ODOO_DB, uid, ODOO_PASSWORD,
                        'vehicle.booking', 'read',
                        [[booking_id], ['destination_latitude', 'destination_longitude']]
                    )[0]
                    
                    lat = updated.get('destination_latitude', 0.0)
                    lng = updated.get('destination_longitude', 0.0)
                    
                    if lat and lng and lat != 0.0 and lng != 0.0:
                        print(f"✅ Success! Coordinates: ({lat}, {lng})")
                        success_count += 1
                    else:
                        print(f"⚠️  Failed to geocode (no coordinates returned)")
                        fail_count += 1
                else:
                    print(f"❌ Failed to update booking")
                    fail_count += 1
                    
            except Exception as e:
                print(f"❌ Error: {str(e)}")
                fail_count += 1
        
        # 6. สรุปผล
        print("\n" + "="*60)
        print("📊 Geocoding Summary")
        print("="*60)
        print(f"✅ Success: {success_count}")
        print(f"❌ Failed:  {fail_count}")
        print(f"📋 Total:   {len(bookings)}")
        print("="*60)
        
        if success_count > 0:
            print("\n✅ Geocoding completed successfully!")
        else:
            print("\n⚠️  No bookings were geocoded. Check your Google Maps API Key in Odoo:")
            print("   Settings → Technical → System Parameters → google_maps_api_key")
        
    except Exception as e:
        print(f"\n❌ Fatal Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
