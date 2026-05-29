#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ดูและอัพเดทค่า tracking_interval ใน tracking.settings
"""

import psycopg2
import sys

print("=" * 70)
print(" ตรวจสอบและอัพเดท tracking_interval")
print("=" * 70)
print()

# Database config - แก้ให้ตรงกับของคุณ
DB_CONFIG = {
    'host': 'localhost',
    'port': '5432',
    'database': 'odoo18',
    'user': 'postgres',  # ลอง postgres แทน odoo
    'password': 'admin'
}

def check_and_update():
    try:
        print("🔌 Connecting to PostgreSQL...")
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("✅ Connected!")
        print()
        
        # 1. ดูค่าปัจจุบัน
        print("📊 Current values in tracking_settings:")
        print("-" * 70)
        
        cursor.execute("""
            SELECT 
                ts.id,
                ru.login,
                ts.tracking_interval
            FROM tracking_settings ts
            LEFT JOIN res_users ru ON ts.user_id = ru.id
            ORDER BY ts.id
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("⚠️  No records found in tracking_settings")
            print("Please create settings in Odoo first")
            cursor.close()
            conn.close()
            return
        
        for setting_id, username, interval in rows:
            print(f"ID: {setting_id}")
            print(f"User: {username}")
            print(f"⏱️  tracking_interval: {interval} minutes")
            print("-" * 70)
        
        # 2. ถามว่าจะอัพเดทไหม
        print()
        print("Do you want to update tracking_interval to 30 minutes?")
        print("This will update ALL users' settings")
        answer = input("Type 'yes' to update: ").strip().lower()
        
        if answer == 'yes':
            print()
            print("🔄 Updating all records to 30 minutes...")
            
            cursor.execute("""
                UPDATE tracking_settings
                SET tracking_interval = 30
                WHERE tracking_interval != 30
            """)
            
            updated = cursor.rowcount
            conn.commit()
            
            print(f"✅ Updated {updated} record(s)")
            print()
            
            # 3. แสดงค่าหลังอัพเดท
            print("📊 After update:")
            print("-" * 70)
            
            cursor.execute("""
                SELECT 
                    ts.id,
                    ru.login,
                    ts.tracking_interval
                FROM tracking_settings ts
                LEFT JOIN res_users ru ON ts.user_id = ru.id
                ORDER BY ts.id
            """)
            
            rows = cursor.fetchall()
            for setting_id, username, interval in rows:
                print(f"ID: {setting_id} | User: {username} | Interval: {interval} min")
            
            print()
            print("=" * 70)
            print(" SUCCESS!")
            print("=" * 70)
            print()
            print("Next steps:")
            print("1. Logout from Odoo")
            print("2. Clear browser cache (Ctrl+Shift+Del)")
            print("3. Close ALL browser windows")
            print("4. Open browser and login again")
            print("5. Test: Open Vehicle Booking > Click 'ตำแหน่ง GPS'")
            print()
        else:
            print("❌ Update cancelled")
        
        cursor.close()
        conn.close()
        
    except psycopg2.OperationalError as e:
        print(f"❌ Connection Error: {e}")
        print()
        print("Please check:")
        print("1. PostgreSQL is running")
        print("2. Database name is correct (currently: odoo18)")
        print("3. Username/password is correct")
        print()
        print("Common usernames: postgres, odoo")
        print("Try changing DB_CONFIG in this script")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    try:
        check_and_update()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
    
    print()
    input("Press Enter to exit...")
