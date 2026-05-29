import xmlrpc.client

# เชื่อมต่อ Odoo
url = 'http://localhost:8078'
db = 'vehicle_booking'
username = 'admin@gmail.com'  # เปลี่ยนเป็น email ของคุณ
password = 'Admin123'

# Authenticate
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})

if uid:
    print(f"✅ เข้าสู่ระบบสำเร็จ! User ID: {uid}")
    
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    
    # เรียก get_user_settings()
    result = models.execute_kw(db, uid, password,
        'tracking.settings', 'get_user_settings',
        [uid])
    
    print("\n📋 ค่าที่ Controller จะได้รับ:")
    print(f"   tracking_interval: {result.get('tracking_interval')} นาที")
    print(f"   tracking_enabled: {result.get('tracking_enabled')}")
    print(f"\n⏱️  แผนที่ควรรีเฟรชทุก {result.get('tracking_interval')} นาที")
    
else:
    print("❌ เข้าสู่ระบบไม่สำเร็จ!")
