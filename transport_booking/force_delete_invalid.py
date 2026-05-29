#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Force Delete Invalid Records - Python Method
ไม่ต้องใช้ psql
"""

import psycopg2
from psycopg2 import sql
import sys

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Npd_Transport',
    'user': 'odoo',
    'password': 'odoo',
}

def main():
    print()
    print("=" * 60)
    print("🔧 Force Delete Invalid Records")
    print("=" * 60)
    print()
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # ขั้นตอนที่ 1: ลบ constraint
        print("⚠️  ขั้นตอนที่ 1: ลบ Foreign Key Constraint เก่า...")
        try:
            cursor.execute("""
                ALTER TABLE vehicle_tracking 
                DROP CONSTRAINT IF EXISTS vehicle_tracking_driver_id_fkey CASCADE
            """)
            conn.commit()
            print("✅ ลบ Constraint เสร็จแล้ว")
        except Exception as e:
            print(f"⚠️  {e}")
            conn.rollback()
        
        print()
        
        # ขั้นตอนที่ 2: ลบข้อมูล invalid
        print("⚠️  ขั้นตอนที่ 2: ลบข้อมูล invalid...")
        cursor.execute("""
            DELETE FROM vehicle_tracking 
            WHERE driver_id NOT IN (
                SELECT id FROM vehicle_driver WHERE id IS NOT NULL
            ) 
            AND driver_id IS NOT NULL
        """)
        deleted = cursor.rowcount
        conn.commit()
        print(f"✅ ลบ {deleted} records ที่ไม่ถูกต้อง")
        
        print()
        
        # ขั้นตอนที่ 3: ตรวจสอบ
        print("✅ ขั้นตอนที่ 3: ตรวจสอบผลลัพธ์...")
        cursor.execute("SELECT COUNT(*) FROM vehicle_tracking")
        total = cursor.fetchone()[0]
        print(f"   Records ทั้งหมด: {total}")
        
        # ตรวจสอบว่ายังมี invalid หรือไม่
        cursor.execute("""
            SELECT COUNT(*) FROM vehicle_tracking 
            WHERE driver_id IS NOT NULL
            AND driver_id NOT IN (SELECT id FROM vehicle_driver)
        """)
        remaining = cursor.fetchone()[0]
        print(f"   Invalid records: {remaining}")
        
        if remaining == 0:
            print()
            print("=" * 60)
            print("✅ เสร็จแล้ว! พร้อม Restart Odoo")
            print("=" * 60)
        else:
            print()
            print("❌ ยังมี invalid records เหลืออยู่!")
            print("=" * 60)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print()
        print(f"❌ ข้อผิดพลาด: {e}")
        print()
        print("ตรวจสอบ:")
        print("  - PostgreSQL service กำลังรันอยู่หรือไม่?")
        print("  - Database name ถูกต้องหรือไม่?")
        print("  - Username/Password ถูกต้องหรือไม่?")
        return False
    
    return True

if __name__ == '__main__':
    success = main()
    input("\nกด Enter เพื่อออก...")
    sys.exit(0 if success else 1)
