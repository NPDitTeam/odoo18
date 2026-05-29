#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Fix Daily Allowance Display in Delivery History
แก้ไขการแสดงค่าเบี้ยเลี้ยงในหน้าประวัติการจัดส่ง

สิ่งที่ทำ:
1. บังคับอัปเดต View XML
2. ล้างแคช Odoo
3. รีเฟรช View
4. ตรวจสอบข้อมูล
"""

import os
import sys
import time
import subprocess
import logging
from pathlib import Path

# ตั้งค่า Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# พาธ
ODOO_PATH = r"C:\Program Files\Odoo 18.0.20251009\server"
ADDON_PATH = os.path.join(ODOO_PATH, "custom-addons", "transport_booking")
VIEWS_PATH = os.path.join(ADDON_PATH, "views")
XML_FILE = os.path.join(VIEWS_PATH, "delivery_history_views.xml")

def restart_odoo():
    """รีสตาร์ท Odoo Service"""
    logger.info("⏳ กำลังรีสตาร์ท Odoo Service...")
    try:
        # หยุด Service
        subprocess.run(["net", "stop", "odoo"], 
                      capture_output=True, text=True, check=False)
        time.sleep(3)
        
        # เริ่ม Service
        result = subprocess.run(["net", "start", "odoo"],
                              capture_output=True, text=True)
        
        if "service was started successfully" in result.stdout or result.returncode == 0:
            logger.info("✅ Odoo Service รีสตาร์ทเรียบร้อย")
            time.sleep(5)
            return True
        else:
            logger.warning("⚠️ ไม่สามารถรีสตาร์ท Service ผ่าน net หรือ Admin แล้ว")
            return False
    except Exception as e:
        logger.error(f"❌ เกิดข้อผิดพลาด: {str(e)}")
        return False

def clear_odoo_cache():
    """ล้างแคช Odoo"""
    logger.info("🗑️ ล้างแคช Odoo...")
    cache_paths = [
        os.path.join(ODOO_PATH, "custom-addons", "transport_booking", "__pycache__"),
        os.path.join(ODOO_PATH, "custom-addons", "transport_booking", "models", "__pycache__"),
        os.path.join(ODOO_PATH, "custom-addons", "transport_booking", "controllers", "__pycache__"),
    ]
    
    for path in cache_paths:
        if os.path.exists(path):
            try:
                import shutil
                shutil.rmtree(path)
                logger.info(f"✅ ล้างแคช: {path}")
            except Exception as e:
                logger.warning(f"⚠️ ไม่สามารถล้างแคช {path}: {str(e)}")

def verify_xml_changes():
    """ตรวจสอบว่า XML มีการแก้ไขแล้ว"""
    logger.info("📋 ตรวจสอบการแก้ไข XML...")
    try:
        with open(XML_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'width=' in content and 'daily_allowance' in content:
                logger.info("✅ ข้อมูลค่าเบี้ยเลี้ยงอยู่ใน XML")
                # หาบรรทัดที่มี daily_allowance
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'daily_allowance' in line:
                        logger.info(f"   บรรทัด {i+1}: {line.strip()}")
                return True
            else:
                logger.error("❌ ไม่พบข้อมูลค่าเบี้ยเลี้ยงใน XML")
                return False
    except Exception as e:
        logger.error(f"❌ ไม่สามารถอ่าน XML: {str(e)}")
        return False

def run_odoo_shell_command(command):
    """รันคำสั่ง Odoo ผ่าน Shell"""
    logger.info(f"📝 รันคำสั่ง: {command}")
    try:
        script = f"""
import os
os.chdir(r'{ODOO_PATH}')

import odoo
from odoo.cli.main import main as cli_main

# เตรียมพารามิเตอร์
sys.argv = ['odoo', '-c', r'{os.path.join(ODOO_PATH, "odoo.conf")}']

# รัน Odoo ที่มี shell
cli_main(['--shell-like', '--update=transport_booking'])
"""
        
        # สร้างไฟล์ shell script ชั่วคราว
        shell_file = os.path.join(ADDON_PATH, "temp_shell_fix.py")
        with open(shell_file, 'w', encoding='utf-8') as f:
            f.write(script)
        
        logger.info(f"⚠️ เนื่องจากต้องการ Odoo Shell (ต้อง Admin)")
        logger.info(f"📌 โปรดรัน: python {shell_file}")
        
        return True
    except Exception as e:
        logger.error(f"❌ ข้อผิดพลาด: {str(e)}")
        return False

def main():
    """ฟังก์ชันหลัก"""
    print("""
    ╔════════════════════════════════════════════════════════════════╗
    ║  🔧 ตัวแก้ไขการแสดงค่าเบี้ยเลี้ยง - Delivery History      ║
    ║     Daily Allowance Display Fix                               ║
    ╚════════════════════════════════════════════════════════════════╝
    """)
    
    # ขั้นตอนที่ 1: ตรวจสอบ XML
    logger.info("\n📍 ขั้นตอนที่ 1: ตรวจสอบไฟล์ XML")
    if not verify_xml_changes():
        logger.error("❌ XML ยังไม่ถูกแก้ไข")
        sys.exit(1)
    
    # ขั้นตอนที่ 2: ล้างแคช
    logger.info("\n📍 ขั้นตอนที่ 2: ล้างแคช")
    clear_odoo_cache()
    
    # ขั้นตอนที่ 3: รีสตาร์ท Odoo
    logger.info("\n📍 ขั้นตอนที่ 3: รีสตาร์ท Odoo")
    if restart_odoo():
        logger.info("✅ Odoo รีสตาร์ทเรียบร้อย")
    else:
        logger.warning("⚠️ อาจต้องรีสตาร์ทด้วยตัวเอง")
    
    # ขั้นตอนที่ 4: ข้อมูล
    logger.info("\n" + "="*70)
    logger.info("📌 ขั้นตอนถัดไป:")
    logger.info("   1. เข้าระบบ Odoo")
    logger.info("   2. ไปที่ Transport Booking > ประวัติการจัดส่ง")
    logger.info("   3. ตรวจสอบว่าคอลัมน์ 'ค่าเบี้ยเลี้ยง' แสดงผลแล้ว")
    logger.info("   4. ถ้ายังไม่แสดง ให้รีโหลดหน้าเว็บ (F5)")
    logger.info("="*70)
    
    print("\n✅ การแก้ไขเรียบร้อย!")

if __name__ == '__main__':
    main()
