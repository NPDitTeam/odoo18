#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to geocode all existing bookings
Run from Odoo shell or as a scheduled action
"""

def geocode_all_bookings():
    """Geocode all bookings that don't have coordinates"""
    print("🌍 Starting to geocode all bookings...")
    
    try:
        # ตั้ง API key ก่อน
        IrConfigParameter = env['ir.config_parameter'].sudo()
        api_key = IrConfigParameter.get_param('google_maps_api_key')
        
        if not api_key:
            print("⚠️  Setting Google Maps API key...")
            IrConfigParameter.set_param('google_maps_api_key', 'AIzaSyAorvWR_BL6tgkNgkkRO4NIb8ZTKq92S3U')
            print("✅ API key set successfully")
        else:
            print(f"✅ API key already exists: {api_key[:20]}...")
        
        # หา bookings ที่ยังไม่มีพิกัด
        bookings = env['vehicle.booking'].search([
            '|',
            ('destination_latitude', '=', False),
            ('destination_latitude', '=', 0.0)
        ])
        
        print(f"📦 Found {len(bookings)} bookings without destination coordinates")
        
        success_count = 0
        failed_count = 0
        
        for booking in bookings:
            try:
                print(f"\n🔄 Processing: {booking.name}")
                print(f"   Destination: {booking.destination}")
                
                if booking.destination:
                    # Geocode destination
                    dest_lat, dest_lng = booking._geocode_address(booking.destination)
                    
                    if dest_lat and dest_lng:
                        booking.write({
                            'destination_latitude': dest_lat,
                            'destination_longitude': dest_lng
                        })
                        print(f"   ✅ Updated: ({dest_lat}, {dest_lng})")
                        success_count += 1
                    else:
                        print(f"   ⚠️  Could not geocode")
                        failed_count += 1
                else:
                    print(f"   ⚠️  No destination address")
                    failed_count += 1
                
                # Geocode pickup if needed
                if booking.pickup_location and (not booking.pickup_latitude or booking.pickup_latitude == 0.0):
                    pickup_lat, pickup_lng = booking._geocode_address(booking.pickup_location)
                    if pickup_lat and pickup_lng:
                        booking.write({
                            'pickup_latitude': pickup_lat,
                            'pickup_longitude': pickup_lng
                        })
                        print(f"   ✅ Pickup updated: ({pickup_lat}, {pickup_lng})")
                
            except Exception as e:
                print(f"   ❌ Error: {str(e)}")
                failed_count += 1
                continue
        
        print("\n" + "="*50)
        print(f"✅ Geocoding completed!")
        print(f"   Success: {success_count}")
        print(f"   Failed: {failed_count}")
        print("="*50)
        
        env.cr.commit()
        print("💾 Changes committed to database")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

# Run the function
if __name__ == '__main__' or 'env' in globals():
    geocode_all_bookings()
