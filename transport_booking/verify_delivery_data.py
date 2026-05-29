#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
🔍 Odoo Data Verification Script
ตรวจสอบข้อมูลการจัดส่งใน Odoo Database

ใช้วิธี:
1. cd C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking
2. python verify_delivery_data.py

หรือ:
   cd C:\Program Files\Odoo 18.0.20251009\server
   python -m custom-addons.transport_booking.verify_delivery_data
"""

import sys
import os

# เพิ่มเส้นทาง Odoo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def verify_with_odoo():
    """
    ตรวจสอบข้อมูลโดยใช้ Odoo ORM
    """
    try:
        import odoo
        from odoo import api, SUPERUSER_ID
        from odoo.cli import main as odoo_main
        
        print("=" * 70)
        print("🔍 ODOO DATA VERIFICATION SCRIPT")
        print("=" * 70)
        print()
        
        # โหลด Odoo
        odoo.tools.config['db_name'] = 'odoo'
        registry = odoo.modules.registry.Registry.new('odoo')
        
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            print("📊 [1] บัญชีล่าสุดใน vehicle.booking")
            print("-" * 70)
            bookings = env['vehicle.booking'].search([], order='id desc', limit=5)
            
            for booking in bookings:
                print(f"\n  📦 {booking.name}")
                print(f"     State: {booking.state}")
                print(f"     actual_delivery_time: {booking.actual_delivery_time}")
                print(f"     delivery_timestamp: {booking.delivery_timestamp}")
                print(f"     travel_expenses: {booking.travel_expenses}")
                print(f"     daily_allowance: {booking.daily_allowance}")
                print(f"     shipping_cost: {booking.shipping_cost}")
            
            print("\n" + "=" * 70)
            print("📜 [2] ประวัติการจัดส่งล่าสุด")
            print("-" * 70)
            
            histories = env['delivery.history'].search([], order='id desc', limit=5)
            
            for history in histories:
                print(f"\n  📋 {history.name}")
                print(f"     State: {history.state}")
                print(f"     actual_delivery_time: {history.actual_delivery_time}")
                print(f"     travel_expenses: {history.travel_expenses}")
                print(f"     daily_allowance: {history.daily_allowance}")
                print(f"     shipping_cost: {history.shipping_cost}")
                print(f"     completion_date: {history.completion_date}")
            
            print("\n" + "=" * 70)
            print("🔗 [3] การจับคู่ booking → history")
            print("-" * 70)
            
            done_bookings = env['vehicle.booking'].search([('state', '=', 'done')], order='id desc', limit=5)
            
            for booking in done_bookings:
                history = env['delivery.history'].search([('booking_id', '=', booking.id)], limit=1)
                
                print(f"\n  Booking: {booking.name}")
                if history:
                    print(f"     ✅ มี history: {history.name} (ID: {history.id})")
                    print(f"     booking.actual_delivery_time: {booking.actual_delivery_time}")
                    print(f"     history.actual_delivery_time: {history.actual_delivery_time}")
                    print(f"     booking.travel_expenses: {booking.travel_expenses}")
                    print(f"     history.travel_expenses: {history.travel_expenses}")
                    
                    # ตรวจสอบความแตกต่าง
                    if booking.actual_delivery_time != history.actual_delivery_time:
                        print(f"     ⚠️  ⚠️ MISMATCH: actual_delivery_time แตกต่าง!")
                    
                    if booking.travel_expenses != history.travel_expenses:
                        print(f"     ⚠️  ⚠️ MISMATCH: travel_expenses แตกต่าง!")
                else:
                    print(f"     ❌ ไม่มี history!")
            
            print("\n" + "=" * 70)
            print("📊 [4] สถิติ")
            print("-" * 70)
            
            total_bookings = env['vehicle.booking'].search_count([])
            done_bookings = env['vehicle.booking'].search_count([('state', '=', 'done')])
            total_histories = env['delivery.history'].search_count([])
            completed_histories = env['delivery.history'].search_count([('state', '=', 'completed')])
            
            print(f"\n  vehicle.booking:")
            print(f"     - ทั้งหมด: {total_bookings}")
            print(f"     - เสร็จสิ้น (state='done'): {done_bookings}")
            
            print(f"\n  delivery.history:")
            print(f"     - ทั้งหมด: {total_histories}")
            print(f"     - เสร็จสิ้น (state='completed'): {completed_histories}")
            
            # ตรวจสอบ booking ที่เสร็จแต่ไม่มี history
            orphan_bookings = env['vehicle.booking'].search([
                ('state', '=', 'done'),
                ('id', 'not in', env['delivery.history'].search([]).mapped('booking_id').ids)
            ])
            
            if orphan_bookings:
                print(f"\n  ⚠️  Booking ที่เสร็จแต่ไม่มี history: {len(orphan_bookings)}")
                for booking in orphan_bookings[:5]:
                    print(f"     - {booking.name} (ID: {booking.id})")
            
            print("\n" + "=" * 70)
            print("✅ VERIFICATION COMPLETED")
            print("=" * 70)
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

def verify_with_sql():
    """
    ตรวจสอบข้อมูลโดยใช้ SQL โดยตรง
    """
    try:
        import psycopg2
        
        # เชื่อมต่อ PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            database="odoo",
            user="odoo",
            password="odoo"
        )
        cursor = conn.cursor()
        
        print("=" * 70)
        print("🔍 SQL VERIFICATION")
        print("=" * 70)
        
        # 1. ตรวจสอบ vehicle.booking ล่าสุด
        print("\n📊 [1] vehicle.booking ล่าสุด 5 รายการ")
        print("-" * 70)
        
        cursor.execute("""
            SELECT 
                id, name, state,
                actual_delivery_time,
                delivery_timestamp,
                travel_expenses,
                daily_allowance
            FROM vehicle_booking
            ORDER BY id DESC
            LIMIT 5
        """)
        
        for row in cursor.fetchall():
            id_, name, state, actual_del, delivery_ts, travel, daily = row
            print(f"\n  {name} (ID: {id_})")
            print(f"     State: {state}")
            print(f"     actual_delivery_time: {actual_del}")
            print(f"     delivery_timestamp: {delivery_ts}")
            print(f"     travel_expenses: {travel}")
            print(f"     daily_allowance: {daily}")
        
        # 2. ตรวจสอบ delivery.history ล่าสุด
        print("\n" + "=" * 70)
        print("📜 [2] delivery.history ล่าสุด 5 รายการ")
        print("-" * 70)
        
        cursor.execute("""
            SELECT 
                id, name, state,
                actual_delivery_time,
                travel_expenses,
                daily_allowance,
                completion_date
            FROM delivery_history
            ORDER BY id DESC
            LIMIT 5
        """)
        
        for row in cursor.fetchall():
            id_, name, state, actual_del, travel, daily, completion = row
            print(f"\n  {name} (ID: {id_})")
            print(f"     State: {state}")
            print(f"     actual_delivery_time: {actual_del}")
            print(f"     travel_expenses: {travel}")
            print(f"     daily_allowance: {daily}")
            print(f"     completion_date: {completion}")
        
        conn.close()
        print("\n✅ SQL VERIFICATION COMPLETED")
        
    except Exception as e:
        print(f"⚠️  SQL verification not available: {str(e)}")
        print("   (ข้อมูลจะถูกตรวจสอบจากหน้า Odoo web interface แทน)")

if __name__ == '__main__':
    print("\n🔍 ODOO DELIVERY DATA VERIFICATION\n")
    
    # ลองใช้ SQL ก่อน
    verify_with_sql()
    
    # หรือใช้ Odoo ORM
    # verify_with_odoo()
