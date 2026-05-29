    @http.route('/api/settings/get', type='json', auth='user', methods=['POST'], csrf=False)
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
