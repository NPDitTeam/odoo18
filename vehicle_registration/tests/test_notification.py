# -*- coding: utf-8 -*-
"""
Test Script สำหรับทดสอบการแจ้งเตือน Vehicle Maintenance

วิธีใช้:
1. ไปที่ Settings > Technical > Scheduled Actions
2. หรือใช้ Python console เพื่อรันทดสอบทันที

"""

# =============== วิธี 1: ทดสอบผ่าน UI (ง่ายที่สุด) ===============

"""
ขั้นตอน:
1. ไปที่ Fleet > การซ่อมบำรุง > ประวัติการซ่อม
2. สร้างบันทึกการซ่อมใหม่ (ถ้ายังไม่มี)
3. ไปที่ Fleet > การซ่อมบำรุง > การแจ้งเตือน
4. สร้าง Record ใหม่:
   - เลือก "การซ่อม" (Maintenance History)
   - ตั้งค่า "แจ้งเตือนทุก (วัน)" = 1 (เพื่อทดสอบ)
   - ตั้ง "วันที่เริ่มแจ้งเตือน" = วันนี้
   - เปิด "เปิดการแจ้งเตือน" ✓
   - เลือก "ผู้รับแจ้งเตือน" (ตัวคุณเอง)
5. คลิกปุ่ม "🚀 ส่งแจ้งเตือนตอนนี้"
   → จะเห็นการแจ้งเตือนในช่อง Inbox ด้านบนขวา
6. ดูประวัติที่ส่งแล้วใน "ประวัติการแจ้งเตือน"
"""

# =============== วิธี 2: ทดสอบผ่าน Python Console ===============

"""
เข้า Odoo UI → Settings > Tools > Python Console

Copy-Paste ดังนี้:
"""

# ===== CODE สำหรับ PASTE ใน Python Console =====
"""
# ค้นหาการซ่อมครั้งสุดท้าย
maintenance = env['vehicle.maintenance.history'].search([], limit=1, order='create_date desc')
if not maintenance:
    print("❌ ไม่มีบันทึกการซ่อม กรุณาสร้างก่อน")
else:
    print(f"✅ พบการซ่อม: {maintenance.name}")
    
    # ค้นหาหรือสร้าง Notification
    notification = env['vehicle.maintenance.notification'].search([
        ('maintenance_id', '=', maintenance.id)
    ], limit=1)
    
    if not notification:
        # สร้าง Notification ใหม่
        notification = env['vehicle.maintenance.notification'].create({
            'maintenance_id': maintenance.id,
            'notification_enabled': True,
            'notification_interval': 1,  # 1 วันสำหรับทดสอบ
            'recipient_ids': [(6, 0, [env.user.id])],  # ส่งถึงตัวเอง
        })
        print(f"✅ สร้าง Notification ใหม่: {notification.id}")
    else:
        print(f"✅ พบ Notification เดิม: {notification.id}")
    
    # ส่งแจ้งเตือนทันที
    notification.action_send_notification()
    print("✅ ส่งแจ้งเตือนสำเร็จ!")
    print(f"📊 จำนวนครั้งที่ส่ง: {notification.notification_count}")
    print(f"⏰ ส่งครั้งสุดท้าย: {notification.notification_last_sent}")
    
    # ดูประวัติการส่ง
    history = env['notification.history'].search([
        ('maintenance_id', '=', notification.id)
    ])
    print(f"📝 บันทึกประวัติ: {len(history)} รายการ")
    for h in history:
        print(f"   - {h.title} ({h.status})")
"""

# =============== วิธี 3: ทดสอบ Cron Job ===============

"""
Cron Job จะรันอัตโนมัติทุกวัน
ให้ตั้งค่าใน Settings > Technical > Scheduled Actions

ชื่อ: Vehicle Maintenance Notification Cron
Model: vehicle.maintenance.notification
Method: _cron_send_maintenance_notifications
Interval: 1 day (หรือ 1 hour สำหรับทดสอบ)
"""

# =============== วิธี 4: ทดสอบด้วย Python Script ===============

"""
ใช้ script นี้สำหรับทดสอบในเทอร์มินัล:

python odoo-bin shell -d your_database

แล้ว copy-paste:
"""

def test_notification():
    """ฟังก์ชั่นทดสอบการแจ้งเตือน"""
    from odoo import api
    
    # ค้นหาการซ่อมล่าสุด
    maintenance = env['vehicle.maintenance.history'].search(
        [], limit=1, order='create_date desc'
    )
    
    if not maintenance:
        print("❌ ไม่มีการซ่อมเพื่อทดสอบ")
        return False
    
    print(f"\n{'='*50}")
    print(f"🧪 ทดสอบการแจ้งเตือน")
    print(f"{'='*50}")
    print(f"🚗 รถ: {maintenance.vehicle_id.license_plate}")
    print(f"🔧 การซ่อม: {maintenance.description[:50]}")
    print(f"💰 ค่าใช้จ่าย: {maintenance.cost}")
    
    # ค้นหา Notification
    notification = env['vehicle.maintenance.notification'].search([
        ('maintenance_id', '=', maintenance.id)
    ], limit=1)
    
    if not notification:
        # สร้างใหม่
        notification = env['vehicle.maintenance.notification'].create({
            'maintenance_id': maintenance.id,
            'notification_enabled': True,
            'notification_interval': 1,
            'recipient_ids': [(6, 0, [env.user.id])],
        })
        print(f"✅ สร้าง Notification ID: {notification.id}")
    
    print(f"\n📱 ตั้งค่าการแจ้งเตือน:")
    print(f"   - เปิดใช้งาน: {notification.notification_enabled}")
    print(f"   - ส่งทุก: {notification.notification_interval} วัน")
    print(f"   - ผู้รับ: {len(notification.recipient_ids)} คน")
    
    # ส่งแจ้งเตือน
    print(f"\n🚀 กำลังส่งแจ้งเตือน...")
    notification.action_send_notification()
    
    print(f"✅ ส่งสำเร็จ!")
    print(f"   - จำนวนครั้งที่ส่ง: {notification.notification_count}")
    print(f"   - ส่งครั้งสุดท้าย: {notification.notification_last_sent}")
    
    # ตรวจสอบประวัติ
    history = env['notification.history'].search([
        ('maintenance_id', '=', notification.id)
    ], order='create_date desc', limit=1)
    
    if history:
        print(f"\n📝 ประวัติการส่ง:")
        print(f"   - หัวเรื่อง: {history.title}")
        print(f"   - สถานะ: {history.status}")
        print(f"   - เวลาส่ง: {history.create_date}")
    
    print(f"\n{'='*50}")
    return True

# เรียกใช้
test_notification()
