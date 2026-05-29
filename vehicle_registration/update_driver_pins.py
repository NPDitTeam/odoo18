# -*- coding: utf-8 -*-
"""
สคริปต์สำหรับอัพเดท PIN ให้กับผู้ขับขี่ที่มีอยู่แล้ว

วิธีใช้งาน:
1. เปิด Odoo Shell: python odoo-bin shell -c odoo.conf -d your_database
2. นำโค้ดนี้ไปรันใน shell

หรือ
1. ไปที่ Settings > Technical > Server Actions
2. สร้าง Server Action ใหม่
3. คัดลอกโค้ดส่วน update_pins() ไปวาง
"""

from odoo import api, SUPERUSER_ID
import random


def generate_random_pin():
    """สร้าง PIN 6 หลักแบบสุ่ม"""
    return str(random.randint(100000, 999999))


def update_driver_pins_with_random(env):
    """
    อัพเดท PIN แบบสุ่มให้กับผู้ขับขี่ที่ยังไม่มี PIN
    
    ⚠️ คำเตือน: PIN จะถูกสร้างแบบสุ่ม และต้องแจ้งให้ผู้ขับขี่ทราบในภายหลัง
    """
    Driver = env['vehicle.driver']
    
    # ค้นหาผู้ขับขี่ที่ยังไม่มี PIN
    drivers_without_pin = Driver.search([('pin', '=', False)])
    
    print(f"\n🔍 พบผู้ขับขี่ที่ยังไม่มี PIN จำนวน: {len(drivers_without_pin)} คน\n")
    
    updated_count = 0
    pin_list = []
    
    for driver in drivers_without_pin:
        # สร้าง PIN ใหม่และตรวจสอบว่าไม่ซ้ำ
        while True:
            new_pin = generate_random_pin()
            existing = Driver.search([('pin', '=', new_pin)])
            if not existing:
                break
        
        # อัพเดท PIN
        try:
            driver.write({'pin': new_pin})
            pin_list.append({
                'code': driver.code,
                'name': driver.name,
                'pin': new_pin
            })
            updated_count += 1
            print(f"✅ อัพเดท PIN สำหรับ: {driver.name} (รหัส: {driver.code})")
        except Exception as e:
            print(f"❌ ไม่สามารถอัพเดท PIN สำหรับ {driver.name}: {str(e)}")
    
    print(f"\n📊 สรุปผลการอัพเดท:")
    print(f"   - อัพเดทสำเร็จ: {updated_count} คน")
    print(f"   - ไม่สำเร็จ: {len(drivers_without_pin) - updated_count} คน")
    
    # แสดงรายการ PIN ที่สร้างขึ้น
    if pin_list:
        print(f"\n📋 รายการ PIN ที่สร้างขึ้น:")
        print("=" * 60)
        print(f"{'รหัสพนักงาน':<15} {'ชื่อ-นามสกุล':<30} {'PIN':<10}")
        print("=" * 60)
        for item in pin_list:
            print(f"{item['code']:<15} {item['name']:<30} {item['pin']:<10}")
        print("=" * 60)
        
        # บันทึกลงไฟล์
        try:
            with open('/tmp/driver_pins.txt', 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write(f"{'รหัสพนักงาน':<15} {'ชื่อ-นามสกุล':<30} {'PIN':<10}\n")
                f.write("=" * 60 + "\n")
                for item in pin_list:
                    f.write(f"{item['code']:<15} {item['name']:<30} {item['pin']:<10}\n")
                f.write("=" * 60 + "\n")
            print(f"\n💾 บันทึกรายการ PIN ลงไฟล์: /tmp/driver_pins.txt")
        except Exception as e:
            print(f"\n⚠️ ไม่สามารถบันทึกไฟล์: {str(e)}")
    
    return pin_list


def update_driver_pins_manual(env, pin_mapping):
    """
    อัพเดท PIN แบบกำหนดเองสำหรับผู้ขับขี่
    
    Args:
        env: Odoo environment
        pin_mapping: dict {'driver_code': 'pin', ...}
        
    Example:
        pin_mapping = {
            'DRV001': '123456',
            'DRV002': '654321',
        }
    """
    Driver = env['vehicle.driver']
    
    updated_count = 0
    failed_list = []
    
    print(f"\n🔄 เริ่มอัพเดท PIN สำหรับ {len(pin_mapping)} คน\n")
    
    for driver_code, pin in pin_mapping.items():
        driver = Driver.search([('code', '=', driver_code)], limit=1)
        
        if not driver:
            print(f"⚠️ ไม่พบผู้ขับขี่รหัส: {driver_code}")
            failed_list.append({'code': driver_code, 'reason': 'ไม่พบข้อมูล'})
            continue
        
        try:
            driver.write({'pin': pin})
            updated_count += 1
            print(f"✅ อัพเดท PIN สำหรับ: {driver.name} (รหัส: {driver_code})")
        except Exception as e:
            print(f"❌ ไม่สามารถอัพเดท PIN สำหรับ {driver.name}: {str(e)}")
            failed_list.append({'code': driver_code, 'reason': str(e)})
    
    print(f"\n📊 สรุปผลการอัพเดท:")
    print(f"   - อัพเดทสำเร็จ: {updated_count} คน")
    print(f"   - ไม่สำเร็จ: {len(failed_list)} คน")
    
    if failed_list:
        print(f"\n❌ รายการที่ไม่สำเร็จ:")
        for item in failed_list:
            print(f"   - {item['code']}: {item['reason']}")
    
    return updated_count, failed_list


# ==================== ตัวอย่างการใช้งาน ====================

if __name__ == '__main__':
    # วิธีที่ 1: อัพเดท PIN แบบสุ่มให้กับผู้ขับขี่ทั้งหมดที่ยังไม่มี PIN
    # ใช้เมื่อต้องการสร้าง PIN แบบอัตโนมัติ
    print("\n" + "="*60)
    print("📱 อัพเดท PIN แบบสุ่ม")
    print("="*60)
    
    with api.Environment.manage():
        env = api.Environment(odoo.registry, SUPERUSER_ID, {})
        pin_list = update_driver_pins_with_random(env)
        env.cr.commit()
    
    print("\n✅ เสร็จสิ้น! อย่าลืมแจ้ง PIN ให้กับผู้ขับขี่ทุกคน\n")
    
    # -----------------------------------------------------------
    
    # วิธีที่ 2: อัพเดท PIN แบบกำหนดเอง
    # ใช้เมื่อต้องการกำหนด PIN เอง
    """
    print("\n" + "="*60)
    print("📱 อัพเดท PIN แบบกำหนดเอง")
    print("="*60)
    
    # กำหนด PIN ที่ต้องการ
    my_pin_mapping = {
        'DRV001': '123456',
        'DRV002': '654321',
        'DRV003': '111111',
    }
    
    with api.Environment.manage():
        env = api.Environment(odoo.registry, SUPERUSER_ID, {})
        success, failed = update_driver_pins_manual(env, my_pin_mapping)
        env.cr.commit()
    
    print("\n✅ เสร็จสิ้น!\n")
    """
