# -*- coding: utf-8 -*-
"""
สคริปต์สำหรับ Geocode bookings โดยตรงผ่าน Python method
รัน: python geocode_direct.py
"""

import xmlrpc.client
import sys
import requests
import json

# Odoo Configuration
ODOO_URL = 'http://localhost:8078'
ODOO_DB = 'Npd_Transport'
ODOO_USERNAME = 'Npd_admin'
ODOO_PASSWORD = '1234'

def geocode_address(api_key, address):
    """แปลง address เป็น latitude, longitude"""
    if not address or not address.strip():
        return None, None
    
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'address': address,
            'key': api_key,
            'language': 'th',
            'region': 'th'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'OK' and data.get('results'):
                location = data['results'][0]['geometry']['location']
                lat = location.get('lat')
                lng = location.get('lng')
                return lat, lng
            else:
                print(f"   ⚠️  Geocoding status: {data.get('status')}")
                if data.get('error_message'):
                    print(f"   ⚠️  Error: {data.get('error_message')}")
        else:
            print(f"   ❌ HTTP Error: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Geocoding error: {str(e)}")
    
    return None, None

def main():
    try:
        print("="*60)
        print("🌍 Direct Geocoding for Bookings")
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
        
        # 3. ดึง Google Maps API Key
        print("\n🔑 Getting Google Maps API Key...")
        api_key = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'ir.config_parameter', 'get_param',
            ['google_maps_api_key']
        )
        
        if not api_key:
            print("❌ Google Maps API Key not found!")
            print("   Please set it in Odoo: Settings → Technical → System Parameters")
            sys.exit(1)
        
        print(f"✅ API Key found: {api_key[:10]}...")
        
        # 4. ค้นหา bookings ที่ยังไม่มีพิกัด
        print("\n🔍 Searching for bookings without coordinates...")
        booking_ids = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'vehicle.booking', 'search',
            [[
                '|', '|',
                ['destination_latitude', '=', False],
                ['destination_latitude', '=', 0.0],
                ['destination_longitude', '=', 0.0],
                ['destination', '!=', False]
            ]]
        )
        
        print(f"📋 Found {len(booking_ids)} bookings without coordinates")
        
        if not booking_ids:
            print("✅ All bookings already have coordinates!")
            return
        
        # 5. อ่านข้อมูล bookings
        bookings = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'vehicle.booking', 'read',
            [booking_ids, ['id', 'name', 'destination']]
        )
        
        # 6. Geocode แต่ละ booking
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
            
            # Geocode โดยตรง
            lat, lng = geocode_address(api_key, destination)
            
            if lat and lng:
                # บันทึกพิกัดเข้า Odoo
                try:
                    result = models.execute_kw(
                        ODOO_DB, uid, ODOO_PASSWORD,
                        'vehicle.booking', 'write',
                        [[booking_id], {
                            'destination_latitude': lat,
                            'destination_longitude': lng,
                        }]
                    )
                    
                    if result:
                        print(f"   ✅ Success! Coordinates: ({lat}, {lng})")
                        success_count += 1
                    else:
                        print(f"   ❌ Failed to update booking")
                        fail_count += 1
                        
                except Exception as e:
                    print(f"   ❌ Error updating: {str(e)}")
                    fail_count += 1
            else:
                print(f"   ⚠️  Failed to geocode")
                fail_count += 1
        
        # 7. สรุปผล
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
            print("\n⚠️  No bookings were geocoded.")
            print("   Possible reasons:")
            print("   - Invalid Google Maps API Key")
            print("   - API Key doesn't have Geocoding API enabled")
            print("   - API quota exceeded")
        
    except Exception as e:
        print(f"\n❌ Fatal Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
