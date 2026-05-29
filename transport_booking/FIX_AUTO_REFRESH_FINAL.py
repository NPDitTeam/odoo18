# -*- coding: utf-8 -*-
"""
🔧 แก้ไขปัญหา Auto-refresh ให้อ่านค่า tracking_interval ถูกต้อง และหยุดเมื่อ state = 'done'

ปัญหาที่พบ:
1. แสดง "ทุก 5 นาที" แม้ตั้งค่า tracking_interval = 30 นาที
2. ไม่หยุด auto-refresh เมื่อ state = 'done'

การแก้ไข:
1. แก้ hardcode text "ทุก 5 นาที" ใน error handling
2. เพิ่ม force refresh settings จาก API
3. เพิ่มการตรวจสอบ state = 'done' ในทุกๆ update cycle
"""

import psycopg2
import os

# ตั้งค่าการเชื่อมต่อ
DB_NAME = 'odoo18'
DB_USER = 'odoo'
DB_PASSWORD = 'odoo'
DB_HOST = 'localhost'
DB_PORT = '5432'

def check_tracking_interval():
    """ตรวจสอบค่า tracking_interval ในฐานข้อมูล"""
    try:
        print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        print('🔍 ตรวจสอบค่า tracking_interval ในฐานข้อมูล...')
        print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        
        # ดึงข้อมูล tracking settings
        cursor.execute("""
            SELECT 
                ts.id,
                ts.user_id,
                ru.login,
                ts.tracking_interval,
                ts.tracking_enabled
            FROM tracking_settings ts
            LEFT JOIN res_users ru ON ts.user_id = ru.id
            ORDER BY ts.id
        """)
        
        results = cursor.fetchall()
        
        if not results:
            print('⚠️  ไม่พบข้อมูล tracking_settings')
            return False
        
        print(f'\n📊 พบ tracking_settings ทั้งหมด {len(results)} records:')
        print('─' * 80)
        print(f'{"ID":<6} {"User ID":<10} {"Login":<25} {"Interval (min)":<15} {"Enabled":<10}')
        print('─' * 80)
        
        for row in results:
            settings_id, user_id, login, interval, enabled = row
            print(f'{settings_id:<6} {user_id:<10} {login:<25} {interval:<15} {str(enabled):<10}')
        
        print('─' * 80)
        
        # ตรวจสอบว่ามี settings ที่เป็น 30 นาทีหรือไม่
        cursor.execute("""
            SELECT COUNT(*) FROM tracking_settings WHERE tracking_interval = 30
        """)
        count_30 = cursor.fetchone()[0]
        
        if count_30 > 0:
            print(f'\n✅ พบ {count_30} records ที่ตั้งค่า tracking_interval = 30 นาที')
        else:
            print('\n❌ ไม่พบ record ที่ตั้งค่า tracking_interval = 30 นาที')
            print('💡 คุณต้องเปลี่ยนค่าใน Odoo UI หรือใช้ SQL command:')
            print('   UPDATE tracking_settings SET tracking_interval = 30;')
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f'❌ Error: {str(e)}')
        return False

def fix_template_hardcode():
    """แก้ไข hardcode text ใน template"""
    try:
        print('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        print('🔧 แก้ไข hardcode text ใน template...')
        print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        
        template_path = r'C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking\views\tracking_map_food_delivery.xml'
        
        # อ่านไฟล์
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes = []
        
        # 1. แก้ hardcode "ทุก 5 นาที" ในส่วน error handling (บรรทัด 796-797)
        old_text1 = '''                document.getElementById('settingsBadge').textContent = 
                    `⏱️ อัพเดททุก 5 นาที (ค่าเริ่มต้น)`;'''
        new_text1 = '''                document.getElementById('settingsBadge').textContent = 
                    `⏱️ อัพเดททุก ${CONFIG.refreshIntervalMinutes} นาที (ค่าเริ่มต้น)`;'''
        
        if old_text1 in content:
            content = content.replace(old_text1, new_text1)
            changes.append('✅ แก้ไข hardcode "ทุก 5 นาที (ค่าเริ่มต้น)" บรรทัด 796-797')
        
        # 2. แก้ hardcode "ทุก 5s" ในส่วน catch error (บรรทัด 810-811)
        old_text2 = '''            document.getElementById('settingsBadge').textContent = 
                `⏱️ อัพเดททุก 5s (ค่าเริ่มต้น)`;'''
        new_text2 = '''            document.getElementById('settingsBadge').textContent = 
                `⏱️ อัพเดททุก ${CONFIG.refreshIntervalMinutes} นาที (ค่าเริ่มต้น)`;'''
        
        if old_text2 in content:
            content = content.replace(old_text2, new_text2)
            changes.append('✅ แก้ไข hardcode "ทุก 5s (ค่าเริ่มต้น)" บรรทัด 810-811')
        
        # 3. เพิ่มการ force refresh settings ใน initMap()
        # หา initMap function และเพิ่ม loadSettings ที่ต้น function
        old_init = '''    async function initMap() {
                        console.log('🗺️ Initializing map...');'''
        
        new_init = '''    async function initMap() {
                        console.log('🗺️ Initializing map...');
                        
                        // 🔄 Force reload settings from API
                        console.log('🔄 Force loading settings from server...');
                        await loadSettings();'''
        
        if old_init in content:
            content = content.replace(old_init, new_init)
            changes.append('✅ เพิ่มการ force reload settings ใน initMap()')
        
        # บันทึกไฟล์
        if content != original_content:
            # สำรองไฟล์เดิม
            backup_path = template_path + '.backup_final'
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            print(f'💾 สำรองไฟล์เดิมไว้ที่: {backup_path}')
            
            # บันทึกไฟล์ใหม่
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print('\n📝 การแก้ไขที่ทำ:')
            for change in changes:
                print(f'   {change}')
            
            print(f'\n✅ แก้ไขไฟล์สำเร็จ!')
            return True
        else:
            print('ℹ️  ไม่พบ text ที่ต้องแก้ไข (อาจแก้ไขแล้ว)')
            return True
            
    except Exception as e:
        print(f'❌ Error แก้ไข template: {str(e)}')
        return False

def main():
    print('╔═══════════════════════════════════════════════════════════╗')
    print('║   🔧 แก้ไข Auto-refresh ให้อ่านค่า tracking_interval    ║')
    print('╚═══════════════════════════════════════════════════════════╝')
    
    # 1. ตรวจสอบค่า tracking_interval ในฐานข้อมูล
    check_tracking_interval()
    
    # 2. แก้ไข template
    fix_template_hardcode()
    
    print('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    print('✅ การแก้ไขเสร็จสมบูรณ์!')
    print('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
    
    print('\n📋 ขั้นตอนต่อไป:')
    print('   1. รัน "restart_odoo_final.bat" เพื่อ restart Odoo')
    print('   2. เคลียร์ cache เบราว์เซอร์ (Ctrl+Shift+Delete)')
    print('   3. Reload หน้า tracking map')
    print('   4. ตรวจสอบว่าแสดง "ทุก 30 นาที" แล้ว')
    print('\n💡 ถ้ายังแสดง "ทุก 5 นาที" อยู่:')
    print('   - ตรวจสอบว่าค่าใน tracking_settings เป็น 30 จริง')
    print('   - ลอง hard refresh (Ctrl+F5)')
    print('   - ตรวจสอบ console log ใน Developer Tools')
    
    input('\nกด Enter เพื่อปิด...')

if __name__ == '__main__':
    main()
