# -*- coding: utf-8 -*-
"""
🚚 Simulate Vehicle Tracking for Testing
สคริปต์สำหรับจำลองการเคลื่อนที่ของรถ เพื่อทดสอบระบบติดตาม
"""
import xmlrpc.client
import time
import random
import math
from datetime import datetime

# ⚙️ Configuration
ODOO_URL = 'http://localhost:8069'
DB_NAME = 'odoo_db'  # เปลี่ยนเป็นชื่อฐานข้อมูลของคุณ
USERNAME = 'admin'  # เปลี่ยนเป็น username ของคุณ
PASSWORD = 'admin'  # เปลี่ยนเป็น password ของคุณ

# 📍 Example Route (Bangkok: Siam -> Don Mueang Airport)
START_POINT = {'lat': 13.7563, 'lng': 100.5018}  # Siam
END_POINT = {'lat': 13.9126, 'lng': 100.6069}    # Don Mueang Airport

# 🔧 Settings
UPDATE_INTERVAL = 5  # วินาที (update ทุก 5 วินาที)
SPEED = 60  # km/h (ความเร็วเฉลี่ย)
STEPS = 50  # จำนวนจุดบนเส้นทาง


def connect_odoo():
    """เชื่อมต่อกับ Odoo"""
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DB_NAME, USERNAME, PASSWORD, {})
    
    if not uid:
        raise Exception('❌ ไม่สามารถเชื่อมต่อ Odoo ได้')
    
    print(f'✅ เชื่อมต่อสำเร็จ! User ID: {uid}')
    
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    return uid, models


def interpolate_points(start, end, steps):
    """สร้างจุดกึ่งกลางระหว่าง 2 จุด"""
    points = []
    for i in range(steps + 1):
        ratio = i / steps
        lat = start['lat'] + (end['lat'] - start['lat']) * ratio
        lng = start['lng'] + (end['lng'] - start['lng']) * ratio
        points.append({'lat': lat, 'lng': lng})
    return points


def add_noise(value, max_variation=0.0001):
    """เพิ่ม noise เล็กน้อยให้ดูเหมือนการเคลื่อนที่จริง"""
    return value + random.uniform(-max_variation, max_variation)


def simulate_tracking(booking_id, uid, models):
    """จำลองการติดตามตำแหน่งรถ"""
    print(f'\n🚚 เริ่มจำลองการติดตาม Booking ID: {booking_id}')
    print(f'📍 เส้นทาง: Siam → Don Mueang Airport')
    print(f'⏱️  อัพเดททุก {UPDATE_INTERVAL} วินาที')
    print(f'🏃 ความเร็ว: {SPEED} km/h')
    print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n')
    
    # สร้างเส้นทาง
    route_points = interpolate_points(START_POINT, END_POINT, STEPS)
    
    for i, point in enumerate(route_points):
        # เพิ่ม noise
        lat = add_noise(point['lat'])
        lng = add_noise(point['lng'])
        
        # คำนวณความเร็วแบบสุ่ม (50-70 km/h)
        speed = SPEED + random.uniform(-10, 10)
        
        # คำนวณทิศทาง
        if i < len(route_points) - 1:
            next_point = route_points[i + 1]
            heading = math.degrees(math.atan2(
                next_point['lng'] - point['lng'],
                next_point['lat'] - point['lat']
            ))
        else:
            heading = 0
        
        # สร้างข้อมูล tracking
        tracking_data = {
            'booking_id': booking_id,
            'latitude': lat,
            'longitude': lng,
            'speed': speed,
            'heading': heading,
            'accuracy': random.uniform(5, 15),  # 5-15 เมตร
            'altitude': random.uniform(0, 5),
            'battery_level': max(100 - (i * 2), 10),  # แบตเตอรี่ค่อยๆ ลด
            'is_moving': speed > 5,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        try:
            # บันทึกลง vehicle.tracking
            tracking_id = models.execute_kw(
                DB_NAME, uid, PASSWORD,
                'vehicle.tracking', 'create',
                [tracking_data]
            )
            
            # อัพเดท booking current location
            models.execute_kw(
                DB_NAME, uid, PASSWORD,
                'vehicle.booking', 'write',
                [[booking_id], {
                    'current_latitude': lat,
                    'current_longitude': lng,
                    'gps_last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }]
            )
            
            progress = (i + 1) / len(route_points) * 100
            print(f'✅ [{i+1}/{len(route_points)}] {progress:.1f}% | '
                  f'📍 {lat:.6f}, {lng:.6f} | '
                  f'🚗 {speed:.1f} km/h | '
                  f'🧭 {heading:.1f}° | '
                  f'🔋 {tracking_data["battery_level"]:.0f}%')
            
        except Exception as e:
            print(f'❌ Error: {e}')
            return False
        
        time.sleep(UPDATE_INTERVAL)
    
    print('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    print('✅ จำลองการติดตามเสร็จสิ้น!')
    print('🎉 ถึงปลายทางแล้ว!')
    return True


def main():
    print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    print('🚚 Vehicle Tracking Simulator')
    print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n')
    
    try:
        # เชื่อมต่อ Odoo
        uid, models = connect_odoo()
        
        # ดึง booking ที่มีสถานะ in_progress
        booking_ids = models.execute_kw(
            DB_NAME, uid, PASSWORD,
            'vehicle.booking', 'search',
            [[('state', 'in', ['confirmed', 'in_progress'])]],
            {'limit': 1, 'order': 'id desc'}
        )
        
        if not booking_ids:
            print('❌ ไม่พบ Booking ที่มีสถานะ confirmed หรือ in_progress')
            print('💡 กรุณาสร้าง Booking ใหม่ และเปลี่ยนสถานะเป็น "กำลังขนส่ง" ก่อน')
            return
        
        booking_id = booking_ids[0]
        
        # ดึงข้อมูล booking
        booking = models.execute_kw(
            DB_NAME, uid, PASSWORD,
            'vehicle.booking', 'read',
            [booking_id], {'fields': ['name', 'vehicle_id', 'driver_id', 'state']}
        )[0]
        
        print(f'📦 Booking: {booking["name"]}')
        print(f'🚚 รถ: {booking["vehicle_id"][1] if booking["vehicle_id"] else "ไม่ระบุ"}')
        print(f'👤 คนขับ: {booking["driver_id"][1] if booking["driver_id"] else "ไม่ระบุ"}')
        
        # ยืนยันก่อนเริ่ม
        confirm = input(f'\n❓ ต้องการจำลองการติดตาม Booking นี้หรือไม่? (y/n): ')
        if confirm.lower() != 'y':
            print('❌ ยกเลิกการจำลอง')
            return
        
        # เริ่มจำลอง
        simulate_tracking(booking_id, uid, models)
        
    except KeyboardInterrupt:
        print('\n\n⚠️  หยุดการจำลองโดยผู้ใช้')
    except Exception as e:
        print(f'\n❌ Error: {e}')


if __name__ == '__main__':
    main()
