import xmlrpc.client

# เชื่อมต่อ Odoo
url = 'http://localhost:8078'
db = 'vehicle_booking'
username = 'admin@gmail.com'  # เปลี่ยนเป็น email ของคุณ
password = 'Admin123'  # เปลี่ยนเป็นรหัสผ่านของคุณ

# Authenticate
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})

if uid:
    print(f"✅ เข้าสู่ระบบสำเร็จ! User ID: {uid}")
    
    # เชื่อมต่อ Object
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    
    # ค้นหา tracking.settings ของ user ปัจจุบัน
    settings_ids = models.execute_kw(db, uid, password, 
        'tracking.settings', 'search',
        [[['user_id', '=', uid]]])
    
    if settings_ids:
        print(f"\n✅ พบ tracking.settings สำหรับ user นี้ (ID: {settings_ids[0]})")
        
        # อ่านข้อมูล settings
        settings = models.execute_kw(db, uid, password,
            'tracking.settings', 'read',
            [settings_ids, [
                'tracking_enabled',
                'tracking_interval',
                'high_accuracy',
                'notify_on_arrival',
                'notify_on_delay',
                'show_speed',
                'show_route',
                'map_type'
            ]])
        
        print("\n📋 การตั้งค่าปัจจุบัน:")
        for key, value in settings[0].items():
            if key != 'id':
                print(f"   {key}: {value}")
        
        print(f"\n⏱️  tracking_interval = {settings[0]['tracking_interval']} นาที")
        
    else:
        print("\n❌ ไม่พบ tracking.settings สำหรับ user นี้!")
        print("   กำลังสร้าง settings ใหม่ด้วยค่า default...")
        
        # สร้าง settings ใหม่
        new_id = models.execute_kw(db, uid, password,
            'tracking.settings', 'create',
            [{
                'user_id': uid,
                'tracking_interval': 15  # ตั้งเป็น 15 นาทีตามที่คุณต้องการ
            }])
        
        print(f"   ✅ สร้าง settings สำเร็จ! ID: {new_id}")
        print(f"   ⏱️  tracking_interval = 15 นาที")
        
else:
    print("❌ เข้าสู่ระบบไม่สำเร็จ! ตรวจสอบ username/password")
