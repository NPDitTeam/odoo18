#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Fix Foreign Key Violation - Auto Fix
แก้ไข driver_id ที่ไม่มีจริงในตาราง vehicle_driver
"""

import psycopg2
from psycopg2 import sql
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'Npd_Transport',
    'user': 'odoo',
    'password': 'odoo',  # ⚠️ เปลี่ยนตามของคุณ
}

def connect_db():
    """เชื่อมต่อ PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ ไม่สามารถเชื่อมต่อ Database: {e}")
        return None

def fix_foreign_keys():
    """แก้ไข Foreign Key Violation"""
    
    print("=" * 60)
    print("🔧 Fixing vehicle_tracking Foreign Keys")
    print("=" * 60)
    print()
    
    conn = connect_db()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        # ขั้นตอนที่ 1: นับ records ที่ invalid
        print("📍 ขั้นตอนที่ 1: ตรวจหา records ที่ invalid...")
        cursor.execute("""
            SELECT COUNT(*) FROM vehicle_tracking
            WHERE driver_id IS NOT NULL
            AND driver_id NOT IN (SELECT id FROM vehicle_driver)
        """)
        invalid_count = cursor.fetchone()[0]
        print(f"   พบ {invalid_count} records ที่ไม่ถูกต้อง")
        
        if invalid_count == 0:
            print("   ✅ ไม่มี records ที่ไม่ถูกต้อง - เสร็จแล้ว!")
            cursor.close()
            conn.close()
            return True
        
        # ขั้นตอนที่ 2: ลบ records ที่ driver_id ไม่มีจริง
        print()
        print("🗑️  ขั้นตอนที่ 2: ลบ records ที่ไม่ถูกต้อง...")
        cursor.execute("""
            DELETE FROM vehicle_tracking
            WHERE driver_id IS NOT NULL
            AND driver_id NOT IN (SELECT id FROM vehicle_driver)
        """)
        deleted_count = cursor.rowcount
        conn.commit()
        print(f"   ✅ ลบ {deleted_count} records")
        
        # ขั้นตอนที่ 3: ตรวจสอบ
        print()
        print("✅ ขั้นตอนที่ 3: ตรวจสอบผลลัพธ์...")
        cursor.execute("""
            SELECT COUNT(*) FROM vehicle_tracking
            WHERE driver_id IS NOT NULL
            AND driver_id NOT IN (SELECT id FROM vehicle_driver)
        """)
        remaining_invalid = cursor.fetchone()[0]
        print(f"   Records ที่ยังคง invalid: {remaining_invalid}")
        
        cursor.execute("SELECT COUNT(*) FROM vehicle_tracking")
        total_records = cursor.fetchone()[0]
        print(f"   Records ทั้งหมดใน vehicle_tracking: {total_records}")
        
        if remaining_invalid == 0:
            print()
            print("=" * 60)
            print("✅ เสร็จแล้ว! ลบ records ที่ไม่ถูกต้องสำเร็จ")
            print("=" * 60)
            cursor.close()
            conn.close()
            return True
        else:
            print()
            print("❌ ยังมี records ที่ไม่ถูกต้องเหลืออยู่")
            cursor.close()
            conn.close()
            return False
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return False

if __name__ == '__main__':
    print()
    print("⚠️  ⚠️  ⚠️  ต้องปิด Odoo ก่อน! ⚠️  ⚠️  ⚠️")
    print()
    
    success = fix_foreign_keys()
    
    if success:
        print()
        print("📌 ต่อไป:")
        print("   1. รีสตาร์ท Odoo")
        print("   2. ทดสอบ API")
    else:
        print()
        print("⚠️  มีปัญหา - ตรวจสอบ logs")
    
    input("\nกด Enter เพื่อออก...")
