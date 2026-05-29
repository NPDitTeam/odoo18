#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตรวจสอบค่า tracking_interval จาก Odoo database
"""
import psycopg2
import json

# การตั้งค่า Database
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'odoo18',
    'user': 'odoo',
    'password': 'odoo'
}

def check_tracking_interval():
    """ตรวจสอบค่า tracking_interval ของทุก user"""
    try:
        print('=' * 70)
        print('🔍 ตรวจสอบ tracking_interval จาก Odoo Database')
        print('=' * 70)
        print()
        
        # เชื่อมต่อ database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # ดึงข้อมูลจาก tracking_settings
        query = """
        SELECT 
            ts.id,
            ts.user_id,
            ru.login as user_login,
            ru.name as user_name,
            ts.tracking_interval,
            ts.tracking_enabled,
            ts.high_accuracy,
            ts.show_speed,
            ts.show_route
        FROM tracking_settings ts
        JOIN res_users ru ON ts.user_id = ru.id
        ORDER BY ts.user_id
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        if not results:
            print('⚠️  ไม่พบข้อมูลใน tracking_settings')
            print()
            print('💡 Tip: ลอง login เข้าแอปครั้งแรก เพื่อสร้าง settings')
            return
        
        print(f'📊 พบ {len(results)} records:')
        print()
        
        for row in results:
            setting_id, user_id, login, name, interval, enabled, accuracy, speed, route = row
            
            print(f'👤 User: {name} ({login})')
            print(f'   🆔 ID: {user_id}')
            print(f'   ⚙️  Settings ID: {setting_id}')
            print('-' * 70)
            print(f'   ⏱️  tracking_interval: {interval} นาที')
            print(f'      → แปลงเป็น: {interval * 60} วินาที')
            print(f'      → ความถี่: ส่งตำแหน่งทุก {interval} นาที')
            print(f'   ✅ tracking_enabled: {enabled}')
            print(f'   🎯 high_accuracy: {accuracy}')
            print(f'   🚗 show_speed: {speed}')
            print(f'   🗺️  show_route: {route}')
            print()
        
        print('=' * 70)
        print('✅ ตรวจสอบเสร็จสิ้น')
        print('=' * 70)
        print()
        
        # ตัวอย่าง API Response
        print('📡 ตัวอย่าง API Response (/api/settings/get):')
        print()
        
        if results:
            row = results[0]
            _, _, _, _, interval, enabled, accuracy, speed, route = row
            
            api_response = {
                'result': {
                    'success': True,
                    'data': {
                        'tracking_interval': interval,
                        'tracking_enabled': enabled,
                        'high_accuracy': accuracy,
                        'show_speed': speed,
                        'show_route': route,
                    }
                }
            }
            
            print(json.dumps(api_response, indent=2, ensure_ascii=False))
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f'❌ Database Error: {e}')
        print()
        print('💡 ตรวจสอบ:')
        print('   - PostgreSQL service ทำงานอยู่หรือไม่')
        print('   - Database config ถูกต้องหรือไม่')
        print('   - User/Password ถูกต้องหรือไม่')
    except Exception as e:
        print(f'❌ Error: {e}')

if __name__ == '__main__':
    check_tracking_interval()
