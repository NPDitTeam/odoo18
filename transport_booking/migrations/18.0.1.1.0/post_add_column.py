# -*- coding: utf-8 -*-
"""
🔧 Migration: เพิ่ม column show_all_transport_booking_branches ใน res_users
"""

def migrate(cr, version):
    """
    เพิ่ม column ที่ขาดหาย
    """
    # เพิ่ม column ใน res_users
    cr.execute("""
        ALTER TABLE res_users 
        ADD COLUMN IF NOT EXISTS show_all_transport_booking_branches BOOLEAN DEFAULT FALSE;
    """)
    
    print("✅ Migration: Added show_all_transport_booking_branches column to res_users")
