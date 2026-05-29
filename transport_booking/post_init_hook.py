# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID

def post_init_hook(cr, registry):
    """
    ฟังก์ชันที่รันหลังจากติดตั้ง module
    เพื่อเพิ่มคอลัมน์ใหม่สำหรับลายน้ำ GPS
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    print("🎨 [POST_INIT_HOOK] เริ่มสร้างฟิลด์ลายน้ำ GPS...")
    
    try:
        # เพิ่มคอลัมน์ลายน้ำ
        cr.execute("""
            ALTER TABLE vehicle_booking 
            ADD COLUMN IF NOT EXISTS delivery_timestamp timestamp without time zone;
        """)
        print("✅ เพิ่มคอลัมน์ delivery_timestamp สำเร็จ")
        
        cr.execute("""
            ALTER TABLE vehicle_booking 
            ADD COLUMN IF NOT EXISTS delivery_latitude numeric(10,7);
        """)
        print("✅ เพิ่มคอลัมน์ delivery_latitude สำเร็จ")
        
        cr.execute("""
            ALTER TABLE vehicle_booking 
            ADD COLUMN IF NOT EXISTS delivery_longitude numeric(10,7);
        """)
        print("✅ เพิ่มคอลัมน์ delivery_longitude สำเร็จ")
        
        print("🎨 [POST_INIT_HOOK] สร้างฟิลด์ลายน้ำ GPS เสร็จ!")
        
    except Exception as e:
        print(f"❌ [POST_INIT_HOOK] เกิดข้อผิดพลาด: {e}")
        raise
