#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
แก้ไข /api/settings/get ให้ support force_refresh และเพิ่ม logging
"""

import os
import re

FILE_PATH = r"C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking\controllers\tracking_controller.py"

print("=" * 70)
print(" แก้ไข /api/settings/get API")
print("=" * 70)
print()

# Check if file exists
if not os.path.exists(FILE_PATH):
    print(f"❌ Error: File not found: {FILE_PATH}")
    input("Press Enter to exit...")
    exit(1)

print(f"📄 Reading: {FILE_PATH}")

# Read file
with open(FILE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern เพื่อหา get_user_settings method (อันแรก)
pattern = r"(@http\.route\('/api/settings/get'.*?\n    def get_user_settings\(self, \*\*kwargs\):.*?(?=\n    @http\.route|\n    def [a-z_]+\(self,|\Z))"

# ข้อความใหม่
new_method = '''@http.route('/api/settings/get', type='json', auth='user', methods=['POST'], csrf=False)
    def get_user_settings(self, force_refresh=False, **kwargs):
        """
        ⚙️ API สำหรับดึงการตั้งค่าผู้ใช้
        
        Parameters:
            - force_refresh: Boolean - Force fresh data (no cache)
        
        Returns:
            - success: Boolean
            - data: User settings object
        """
        try:
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.info('⚙️ [Settings API] GET request received')
            _logger.info(f'   👤 User: {request.env.user.name} (ID: {request.env.user.id})')
            _logger.info(f'   🔄 Force Refresh: {force_refresh}')
            _logger.info(f'   📦 kwargs: {kwargs}')
            
            # ดึงการตั้งค่าจากฐานข้อมูล (ไม่ใช้ cache)
            settings_model = request.env['tracking.settings'].sudo()
            
            # ค้นหา settings ของ user
            user_setting = settings_model.search([
                ('user_id', '=', request.env.user.id)
            ], limit=1)
            
            if user_setting:
                _logger.info(f'   ✅ Found settings record ID: {user_setting.id}')
                _logger.info(f'   ⏱️  tracking_interval from DB: {user_setting.tracking_interval} minutes')
            else:
                _logger.warning(f'   ⚠️  No settings found for user {request.env.user.id}, creating default...')
                user_setting = settings_model.create({
                    'user_id': request.env.user.id
                })
                _logger.info(f'   ✅ Created new settings record ID: {user_setting.id}')
            
            # ใช้ method get_user_settings เพื่อ return ข้อมูล
            settings = settings_model.get_user_settings(request.env.user.id)
            
            _logger.info('   📊 Settings to return:')
            _logger.info(f'      - tracking_interval: {settings.get("tracking_interval")} minutes')
            _logger.info(f'      - tracking_enabled: {settings.get("tracking_enabled")}')
            _logger.info(f'      - show_route: {settings.get("show_route")}')
            _logger.info(f'      - show_speed: {settings.get("show_speed")}')
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            
            return {
                'success': True,
                'data': settings
            }
        except Exception as e:
            _logger.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.error(f"❌ [Settings API] Error getting user settings")
            _logger.error(f"   Error: {str(e)}")
            _logger.error(f"   User ID: {request.env.user.id}")
            import traceback
            _logger.error(f"   Traceback: {traceback.format_exc()}")
            _logger.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            
            return {
                'success': False,
                'message': str(e),
                'data': {
                    'tracking_interval': 5,
                    'tracking_enabled': True,
                    'show_route': True,
                    'show_speed': True,
                    'notify_on_arrival': True
                }
            }
    
'''

# Find and replace (first occurrence only)
match = re.search(pattern, content, re.DOTALL)

if match:
    print(f"✅ พบ method get_user_settings")
    print(f"   Position: characters {match.start()} - {match.end()}")
    print(f"   Length: {match.end() - match.start()} characters")
    
    # Replace
    new_content = content[:match.start()] + new_method + content[match.end():]
    
    # Create backup
    backup_path = FILE_PATH + ".api_fix_backup"
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Backup created: {backup_path}")
    
    # Write new content
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"✅ File updated: {FILE_PATH}")
    
    print()
    print("=" * 70)
    print(" SUCCESS!")
    print("=" * 70)
    print()
    print("✅ API method updated successfully!")
    print()
    print("Next steps:")
    print("1. Restart Odoo (QUICK_FIX_AUTO_REFRESH.bat)")
    print("2. Upgrade module (Settings > Apps)")
    print("3. Logout and clear browser cache")
    print("4. Login and test")
    print()
else:
    print("❌ ไม่พบ method get_user_settings")
    print()
    print("กรุณาตรวจสอบ tracking_controller.py")

print()
input("Press Enter to exit...")
