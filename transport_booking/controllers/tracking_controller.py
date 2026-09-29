# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TrackingController(http.Controller):
    
    @http.route('/tracking/map/<int:booking_id>', type='http', auth='user', methods=['GET'])
    def tracking_map_view(self, booking_id, **kwargs):
        """
        🗺️ แสดงแผนที่ติดตามตำแหน่งแบบ Real-time
        """
        try:
            booking = request.env['vehicle.booking'].browse(booking_id)
            if not booking.exists():
                return request.render('transport_booking.tracking_map_error', {
                    'error_message': 'ไม่พบข้อมูลการจองรถ'
                })
            
            # ดึง API Key จาก settings
            IrConfigParam = request.env['ir.config_parameter'].sudo()
            api_key = (
                IrConfigParam.get_param('google_maps_api_key') or
                IrConfigParam.get_param('google.maps_api_key') or
                'AIzaSyAorvWR_BL6tgkNgkkRO4NIb8ZTKq92S3U'
            )
            
            # เตรียมชื่อคนขับ
            driver_name = None
            if booking.driver_id:
                try:
                    # ลองดึง field ต่างๆ
                    if hasattr(booking.driver_id, 'name') and booking.driver_id.name:
                        driver_name = booking.driver_id.name
                    elif hasattr(booking.driver_id, 'display_name') and booking.driver_id.display_name:
                        driver_name = booking.driver_id.display_name
                    else:
                        driver_name = f"คนขับ ID: {booking.driver_id.id}"
                except:
                    driver_name = None
            
            # Fallback to delivery_employee_name
            if not driver_name and booking.delivery_employee_name:
                driver_name = booking.delivery_employee_name
            
            if not driver_name:
                driver_name = 'ไม่ระบุคนขับ'
            
            # ดึง tracking_interval จาก tracking.settings
            settings_model = request.env['tracking.settings']
            user_settings = settings_model.get_user_settings(request.env.user.id)
            refresh_interval = user_settings.get('tracking_interval', 1)  # ✅ ดึงจากฐานข้อมูล ค่าเริ่มต้น 1 นาที
            
            _logger.info(f"🗺️ [Map] Loading map for booking {booking.name}")
            _logger.info(f"🔑 [Map] API Key: {api_key[:20]}...{api_key[-5:] if len(api_key) > 25 else ''}")
            _logger.info(f"👤 [Map] Driver: {driver_name}")
            _logger.info(f"⏱️  [Map] Refresh Interval: {refresh_interval} minutes")
            
            return request.render('transport_booking.tracking_map_food_delivery_style', {
                'booking': booking,
                'api_key': api_key,
                'driver_name': driver_name,
                'refresh_interval': refresh_interval,  # ส่งค่านี้ไปยัง template
            })
        except Exception as e:
            _logger.error(f"❌ Error rendering tracking map: {str(e)}")
            return request.render('transport_booking.tracking_map_error', {
                'error_message': str(e)
            })
    
    @http.route('/api/settings/get', type='json', auth='user', methods=['POST'], csrf=False)
    def get_user_settings_api(self, force_refresh=False, **kwargs):
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
            
            # ✅ เพิ่ม safety check สำหรับ user
            if not request.env.user or not request.env.user.id:
                _logger.error('❌ [Settings API] Cannot get user ID!')
                return {
                    'success': False,
                    'message': 'Cannot get user ID from any method',
                    'data': {
                        'tracking_interval': 5,
                        'tracking_enabled': True,
                        'show_route': True,
                        'show_speed': True,
                        'notify_on_arrival': True
                    }
                }
            
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
            try:
                _logger.error(f"   User ID: {request.env.user.id if request.env.user else 'NO USER'}")
            except:
                _logger.error(f"   User ID: CANNOT ACCESS")
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
    

    @http.route('/api/booking/get_active_job', type='json', auth='user', methods=['POST'], csrf=False)
    def get_active_job(self, driver_id, **kwargs):
        """
        🚚 API สำหรับเช็คว่ามีงานที่กำลังทำอยู่หรือไม่
        
        Parameters:
            - driver_id: ID ของคนขับ
        
        Returns:
            - success: Boolean
            - data: Booking object หรือ null ถ้าไม่มีงานที่กำลังทำ
        """
        try:
            # ค้นหางานที่มีสถานะ in_progress ของ driver คนนี้
            active_booking = request.env['vehicle.booking'].search([
                ('driver_id', '=', int(driver_id)),
                ('state', '=', 'in_progress')
            ], limit=1, order='planned_start_date desc')
            
            if not active_booking:
                return {
                    'success': True,
                    'data': None,
                    'message': 'ไม่มีงานที่กำลังทำอยู่'
                }
            
            # ✅ เตรียม driver_name
            driver_name = None
            if active_booking.driver_id:
                driver_name = active_booking.driver_id.name or f"ID: {active_booking.driver_id.id}"
            
            # ส่งข้อมูล booking กลับไป
            return {
                'success': True,
                'data': {
                    'id': active_booking.id,
                    'name': active_booking.name,
                    'state': active_booking.state,
                    'tracking_status': active_booking.tracking_status,
                    'pickup_location': active_booking.pickup_location,
                    'destination': active_booking.destination,
                    'planned_start_date': active_booking.planned_start_date.isoformat() if active_booking.planned_start_date else None,
                    'planned_end_date': active_booking.planned_end_date.isoformat() if active_booking.planned_end_date else None,
                    'partner_name': active_booking.partner_id.name if active_booking.partner_id else None,
                    'vehicle_name': active_booking.vehicle_id.license_plate if active_booking.vehicle_id else None,
                    'distance_km': active_booking.distance_km,
                    'shipping_cost': active_booking.shipping_cost,
                    'driver_id': active_booking.driver_id.id if active_booking.driver_id else None,
                    'driver_name': driver_name,  # ✅ เพิ่มบรรทัด
                },
                'message': f'พบงานที่กำลังทำอยู่: {active_booking.name}'
            }
        except Exception as e:
            _logger.error(f"❌ Error getting active job: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    @http.route('/api/tracking/update_location', type='json', auth='user', methods=['POST'], csrf=False)
    def update_vehicle_location(self, booking_id, latitude, longitude, speed=0, heading=0, 
                                 accuracy=None, altitude=None, battery_level=None, address=None, **kwargs):
        """
        📍 API สำหรับอัพเดทตำแหน่งรถแบบ Real-time
        
        Parameters:
            - booking_id: ID ของการจองรถ
            - latitude: พิกัด Latitude
            - longitude: พิกัด Longitude
            - speed: ความเร็ว (km/h)
            - heading: ทิศทางการเดินทาง (องศา 0-360)
            - accuracy: ความแม่นยำของ GPS (เมตร)
            - altitude: ความสูงจากระดับน้ำทะเล (เมตร)
            - battery_level: ระดับแบตเตอรี่ (0-100)
            - address: ที่อยู่ปัจจุบัน
        """
        try:
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.info('📍 [API] Received location update request')
            _logger.info(f'   📦 Booking ID: {booking_id}')
            _logger.info(f'   🌐 Coordinates: {latitude}, {longitude}')
            _logger.info(f'   🎯 Accuracy: {accuracy}m' if accuracy else '   🎯 Accuracy: N/A')
            _logger.info(f'   🚗 Speed: {speed} km/h')
            _logger.info(f'   🧭 Heading: {heading}°')
            _logger.info(f'   🔋 Battery: {battery_level}%' if battery_level else '   🔋 Battery: N/A')
            if address:
                _logger.info(f'   📮 Address: {address}')
            
            # ตรวจสอบ booking
            booking = request.env['vehicle.booking'].browse(int(booking_id))
            if not booking.exists():
                _logger.error(f'❌ [API] Booking not found: {booking_id}')
                return {'success': False, 'message': f'ไม่พบข้อมูลการจองรถ ID: {booking_id}'}
            
            _logger.info(f'   ✅ Booking found: {booking.name}')
            _logger.info(f'   📊 Current state: {booking.state}')
            _logger.info(f'   🚚 Vehicle: {booking.vehicle_id.license_plate if booking.vehicle_id else "N/A"}')
            
            # 🛑 ตรวจสอบ: ถ้าสถานะเป็น 'done' (เสร็จสิ้น) ให้หยุดการติดตาม
            if booking.state == 'done':
                _logger.warning('🛑 [API] Booking is DONE - Stop sending location updates!')
                _logger.info('   📍 Generating final map with complete tracking history...')
                
                # เตรียมข้อมูลแผนที่สุดท้าย
                tracking_records = request.env['vehicle.tracking'].search([
                    ('booking_id', '=', booking.id)
                ], order='timestamp asc')
                
                final_map_data = {
                    'tracking_count': len(tracking_records),
                    'start_point': {
                        'latitude': booking.pickup_latitude,
                        'longitude': booking.pickup_longitude,
                        'address': booking.pickup_location,
                    },
                    'end_point': {
                        'latitude': booking.destination_latitude,
                        'longitude': booking.destination_longitude,
                        'address': booking.destination,
                    },
                    'route': []
                }
                
                # เก็บเส้นทางทั้งหมด
                for track in tracking_records:
                    final_map_data['route'].append({
                        'timestamp': track.timestamp.isoformat() if track.timestamp else '',
                        'latitude': track.latitude,
                        'longitude': track.longitude,
                        'speed': track.speed,
                        'heading': track.heading,
                        'address': track.address or '',
                    })
                
                _logger.info(f'   ✅ Final map prepared with {len(tracking_records)} tracking points')
                
                return {
                    'success': False,  # ส่ง False เพื่อให้แอปรู้ว่าต้องหยุด
                    'message': 'การจองสิ้นสุดแล้ว - หยุดการติดตามอัตโนมัติ',
                    'booking_state': 'done',
                    'final_map_data': final_map_data,
                    'should_stop_tracking': True,
                }
            
            _logger.info('   💾 Updating booking current location...')
            update_vals = {
                'current_latitude': float(latitude),
                'current_longitude': float(longitude),
                'gps_last_update': datetime.now(),
            }
            
            # อัพเดท current_location (address) ถ้ามีส่งมา
            if address:
                update_vals['current_location'] = str(address)
                _logger.info(f'   📮 Updating current location: {address}')
            
            booking.write(update_vals)
            _logger.info('   ✅ Booking location updated')
            
            # บันทึกประวัติการติดตาม
            _logger.info('   💾 Creating tracking history record...')
            tracking_vals = {
                'booking_id': booking.id,
                'driver_id': booking.driver_id.id,  # ✅ ต้องมี driver_id เสมอ
                'latitude': float(latitude),
                'longitude': float(longitude),
                'speed': float(speed),
                'heading': float(heading),
                'timestamp': datetime.now(),
            }
            
            # เพิ่มข้อมูลเสริม (ถ้ามี)
            if accuracy is not None:
                tracking_vals['accuracy'] = float(accuracy)
            if altitude is not None:
                tracking_vals['altitude'] = float(altitude)
            if battery_level is not None:
                tracking_vals['battery_level'] = float(battery_level)
            if address:
                tracking_vals['address'] = str(address)
            
            tracking_record = request.env['vehicle.tracking'].create(tracking_vals)
            _logger.info(f'   ✅ Tracking record created: ID {tracking_record.id}')
            
            # เช็คว่ารถออกนอกเส้นทางหรือไม่
            off_route = False
            settings = request.env['tracking.settings'].get_or_create_settings(request.env.user.id)
            
            if settings.notify_off_route and booking.waypoints_json:
                _logger.info('   🔍 Checking off-route status...')
                off_route = self._check_off_route(
                    float(latitude), 
                    float(longitude), 
                    booking.waypoints_json,
                    settings.off_route_distance
                )
                if off_route:
                    _logger.warning(f'   ⚠️  Vehicle is OFF ROUTE! Distance > {settings.off_route_distance}m')
                else:
                    _logger.info('   ✅ Vehicle is on route')
            
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.info('✅ [API] Location update completed successfully')
            _logger.info(f'   📦 Booking: {booking.name}')
            _logger.info(f'   📊 Status: {booking.tracking_status}')
            _logger.info(f'   🚨 Off Route: {off_route}')
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            
            # ✅ เตรียม driver_name
            driver_name = None
            if booking.driver_id:
                driver_name = booking.driver_id.name or f"ID: {booking.driver_id.id}"
            
            return {
                'success': True,
                'message': 'อัพเดทตำแหน่งสำเร็จ',
                'data': {
                    'booking_id': booking.id,
                    'booking_name': booking.name,
                    'current_status': booking.tracking_status,
                    'off_route': off_route,
                    'last_update': datetime.now().isoformat(),
                    'driver_id': booking.driver_id.id if booking.driver_id else None,
                    'driver_name': driver_name,  # ✅ เพิ่มบรรทัด
                }
            }
            
        except Exception as e:
            _logger.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.error(f'❌ [API] ERROR updating location')
            _logger.error(f'   Error: {str(e)}')
            _logger.error(f'   Booking ID: {booking_id}')
            import traceback
            _logger.error(f'   Traceback: {traceback.format_exc()}')
            _logger.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            return {'success': False, 'message': f'เกิดข้อผิดพลาด: {str(e)}'}
    
    def _check_off_route(self, lat, lng, waypoints_json, max_distance):
        """
        เช็คว่าตำแหน่งปัจจุบันออกนอกเส้นทางหรือไม่
        
        Parameters:
            - lat: Latitude ปัจจุบัน
            - lng: Longitude ปัจจุบัน
            - waypoints_json: JSON ของเส้นทาง
            - max_distance: ระยะห่างสูงสุดที่อนุญาต (เมตร)
        
        Returns:
            Boolean: True ถ้าออกนอกเส้นทาง
        """
        import json
        import math
        
        try:
            waypoints = json.loads(waypoints_json) if isinstance(waypoints_json, str) else waypoints_json
            if not waypoints:
                return False
            
            # ฟังก์ชันคำนวณระยะทางระหว่าง 2 จุด (Haversine formula)
            def haversine_distance(lat1, lon1, lat2, lon2):
                R = 6371000  # รัศมีโลกในหน่วยเมตร
                
                lat1_rad = math.radians(lat1)
                lat2_rad = math.radians(lat2)
                delta_lat = math.radians(lat2 - lat1)
                delta_lon = math.radians(lon2 - lon1)
                
                a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                
                return R * c
            
            # หาระยะห่างที่ใกล้ที่สุดจากเส้นทาง
            min_distance = float('inf')
            
            for waypoint in waypoints:
                if isinstance(waypoint, dict) and 'lat' in waypoint and 'lng' in waypoint:
                    distance = haversine_distance(lat, lng, waypoint['lat'], waypoint['lng'])
                    min_distance = min(min_distance, distance)
            
            # ถ้าระยะห่างมากกว่าที่กำหนด ถือว่าออกนอกเส้นทาง
            return min_distance > max_distance
            
        except Exception as e:
            _logger.error(f"❌ Error checking off route: {str(e)}")
            return False
    
    @http.route('/api/tracking/get_active_bookings', type='json', auth='user', methods=['POST'], csrf=False)
    def get_active_bookings(self, driver_id=None, **kwargs):
        """
        🚚 API สำหรับดึงรายการงานขนส่งที่กำลังดำเนินการ
        
        Parameters:
            - driver_id: ID ของคนขับ (ถ้ามี)
        """
        try:
            domain = [('state', 'in', ['confirmed', 'in_progress'])]
            if driver_id:
                domain.append(('driver_id', '=', int(driver_id)))
            
            bookings = request.env['vehicle.booking'].search(domain)
            
            results = []
            for booking in bookings:
                results.append({
                    'id': booking.id,
                    'name': booking.name,
                    'pickup_location': booking.pickup_location,
                    'destination': booking.destination,
                    'state': booking.state,
                    'tracking_status': booking.tracking_status,
                    'vehicle': {
                        'id': booking.vehicle_id.id,
                        'license_plate': booking.vehicle_id.license_plate,
                    } if booking.vehicle_id else None,
                    'driver': {
                        'id': booking.driver_id.id,
                        'name': booking.driver_id.name,
                    } if booking.driver_id else None,
                    'current_location': {
                        'latitude': booking.current_latitude,
                        'longitude': booking.current_longitude,
                        'last_update': booking.gps_last_update.isoformat() if booking.gps_last_update else None,
                    },
                    'planned_start_date': booking.planned_start_date.isoformat() if booking.planned_start_date else None,
                    'planned_end_date': booking.planned_end_date.isoformat() if booking.planned_end_date else None,
                })
            
            return {
                'success': True,
                'data': results,
                'count': len(results)
            }
        except Exception as e:
            _logger.error(f"❌ Error getting active bookings: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    @http.route('/api/tracking/get_tracking_history', type='json', auth='user', methods=['POST'], csrf=False)
    def get_tracking_history(self, booking_id, limit=100, **kwargs):
        """
        📊 API สำหรับดึงประวัติการติดตาม GPS
        
        Parameters:
            - booking_id: ID ของการจองรถ
            - limit: จำนวนข้อมูลที่ต้องการ (default: 100)
        """
        try:
            history = request.env['vehicle.tracking'].search([
                ('booking_id', '=', int(booking_id))
            ], limit=int(limit), order='timestamp desc')
            
            results = []
            for record in history:
                results.append({
                    'timestamp': record.timestamp.isoformat(),
                    'latitude': record.latitude,
                    'longitude': record.longitude,
                    'speed': record.speed,
                    'heading': record.heading,
                })
            
            return {
                'success': True,
                'data': results,
                'count': len(results)
            }
        except Exception as e:
            _logger.error(f"❌ Error getting tracking history: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    @http.route('/api/settings/get', type='json', auth='user', methods=['POST'], csrf=False)
    def get_user_settings(self, **kwargs):
        """
        ⚙️ API สำหรับดึงการตั้งค่าผู้ใช้
        """
        try:
            settings = request.env['tracking.settings'].get_user_settings(request.env.user.id)
            
            return {
                'success': True,
                'data': settings
            }
        except Exception as e:
            _logger.error(f"❌ Error getting settings: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    @http.route('/api/settings/update', type='json', auth='user', methods=['POST'], csrf=False)
    def update_user_settings(self, **kwargs):
        """
        ⚙️ API สำหรับอัพเดทการตั้งค่าผู้ใช้
        
        Parameters:
            - tracking_enabled: Boolean
            - tracking_interval: Integer (seconds)
            - high_accuracy: Boolean
            - notify_on_arrival: Boolean
            - notify_on_delay: Boolean
            - notify_off_route: Boolean
            - off_route_distance: Integer (meters)
            - show_speed: Boolean
            - show_route: Boolean
            - map_type: String (roadmap/satellite/hybrid/terrain)
            - save_history: Boolean
            - history_retention_days: Integer
        """
        try:
            settings = request.env['tracking.settings'].search([
                ('user_id', '=', request.env.user.id)
            ], limit=1)
            
            if not settings:
                settings = request.env['tracking.settings'].create({
                    'user_id': request.env.user.id
                })
            
            vals = {}
            
            # การตั้งค่าการติดตาม
            if 'tracking_enabled' in kwargs:
                vals['tracking_enabled'] = bool(kwargs['tracking_enabled'])
            if 'tracking_interval' in kwargs:
                vals['tracking_interval'] = int(kwargs['tracking_interval'])
            if 'high_accuracy' in kwargs:
                vals['high_accuracy'] = bool(kwargs['high_accuracy'])
            
            # การตั้งค่าการแจ้งเตือน
            if 'notify_on_arrival' in kwargs:
                vals['notify_on_arrival'] = bool(kwargs['notify_on_arrival'])
            if 'notify_on_delay' in kwargs:
                vals['notify_on_delay'] = bool(kwargs['notify_on_delay'])
            if 'notify_off_route' in kwargs:
                vals['notify_off_route'] = bool(kwargs['notify_off_route'])
            if 'off_route_distance' in kwargs:
                vals['off_route_distance'] = int(kwargs['off_route_distance'])
            
            # การตั้งค่าการแสดงผล
            if 'show_speed' in kwargs:
                vals['show_speed'] = bool(kwargs['show_speed'])
            if 'show_route' in kwargs:
                vals['show_route'] = bool(kwargs['show_route'])
            if 'map_type' in kwargs:
                vals['map_type'] = str(kwargs['map_type'])
            
            # การตั้งค่าการบันทึก
            if 'save_history' in kwargs:
                vals['save_history'] = bool(kwargs['save_history'])
            if 'history_retention_days' in kwargs:
                vals['history_retention_days'] = int(kwargs['history_retention_days'])
            
            if vals:
                settings.write(vals)
            
            return {
                'success': True,
                'message': 'บันทึกการตั้งค่าสำเร็จ',
                'data': settings.get_user_settings(request.env.user.id)
            }
        except Exception as e:
            _logger.error(f"❌ Error updating settings: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    @http.route('/api/tracking/update_status', type='json', auth='user', methods=['POST'], csrf=False)
    def update_tracking_status(self, booking_id, status, **kwargs):
        """
        🔄 API สำหรับอัพเดทสถานะการติดตาม
        
        Parameters:
            - booking_id: ID ของการจองรถ
            - status: สถานะใหม่ (pending, picked_up, in_transit, near_destination, delivered)
        """
        try:
            booking = request.env['vehicle.booking'].browse(int(booking_id))
            if not booking.exists():
                return {'success': False, 'message': 'ไม่พบข้อมูลการจองรถ'}

            # คำสั่งนี้มาจากแอปคนขับ ใช้ตั้งแหล่งที่มาให้ถูก
            booking = booking.with_context(npd_from_driver_app=True)
            
            vals = {'tracking_status': status}
            
            # อัพเดทเวลาตามสถานะ
            if status == 'picked_up':
                vals['actual_pickup_time'] = datetime.now()
                vals['planned_start_date_t'] = datetime.now()
            elif status == 'delivered':
                vals['actual_delivery_time'] = datetime.now()
                vals['planned_end_date_t'] = datetime.now()
            
            booking.write(vals)
            
            _logger.info(f"🔄 Status updated for booking {booking.name}: {status}")
            
            return {
                'success': True,
                'message': 'อัพเดทสถานะสำเร็จ',
                'data': {
                    'booking_id': booking.id,
                    'tracking_status': booking.tracking_status,
                }
            }
        except Exception as e:
            _logger.error(f"❌ Error updating status: {str(e)}")
            return {'success': False, 'message': str(e)}

    @http.route('/api/delivery/complete', type='json', auth='user', methods=['POST'], csrf=False)
    def complete_delivery(self, **kwargs):
        """
        ✅ API สำหรับ Complete Delivery พร้อมลายเซ็นและลายน้ำ GPS
        
        Parameters:
            - booking_id: int
            - delivery_photo: base64 string (รูปหลักฐาน)
            - receiver_signature: base64 string (ลายเซ็น)
            - receiver_name: string
            - delivery_photos: list of base64 (รูปหลักฐานเพิ่มเติม)
            - receiver_position: string (ตำแหน่งผู้รับ เช่น เจ้าของบ้าน ยาม)
            - signed_by_self: bool (เซ็นรับแทนเพราะไม่เจอลูกค้า)
            - delivery_timestamp: datetime (เวลาถ่ายรูป)
            - delivery_latitude: float (GPS ละติจูด)
            - delivery_longitude: float (GPS ลองจิจูด)
        """
        try:
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.info('✅ [Complete Delivery] API called')
            
            booking_id = kwargs.get('booking_id')
            delivery_photo = kwargs.get('delivery_photo')
            # แอปรุ่นใหม่ส่ง delivery_photos มาเป็นลิสต์ รุ่นเก่าส่งรูปเดียว
            # ผ่าน delivery_photo เหมือนเดิม ต้องรับได้ทั้งสองแบบ
            delivery_photos = kwargs.get('delivery_photos') or []
            receiver_signature = kwargs.get('receiver_signature')
            receiver_name = kwargs.get('receiver_name')
            receiver_position = kwargs.get('receiver_position')
            signed_by_self = kwargs.get('signed_by_self')
            planned_end_date_t = kwargs.get('planned_end_date_t')  # ✅ เพิ่มเวลาส่งจริง
            delivery_timestamp = kwargs.get('delivery_timestamp')
            delivery_latitude = kwargs.get('delivery_latitude')
            delivery_longitude = kwargs.get('delivery_longitude')
            
            # ✅ แปลง string เป็น datetime object สำหรับ Odoo
            from datetime import datetime, timedelta
            if planned_end_date_t and isinstance(planned_end_date_t, str):
                try:
                    # Parse จาก format "2025-11-21 22:07:33" (Thailand time UTC+7)
                    thailand_time = datetime.strptime(planned_end_date_t, '%Y-%m-%d %H:%M:%S')
                    
                    # ✅ แปลง Thailand time (UTC+7) เป็น UTC ก่อนบันทึก
                    # เพราะ Odoo เก็บเวลาเป็น UTC แล้วแสดงเป็น user timezone
                    planned_end_date_t = thailand_time - timedelta(hours=7)
                    
                    _logger.info(f'   ✅ Converted Thailand time {thailand_time} to UTC: {planned_end_date_t}')
                except Exception as e:
                    _logger.error(f'   ❌ Error parsing planned_end_date_t: {e}')
                    planned_end_date_t = None
            
            _logger.info(f'   📦 Booking ID: {booking_id}')
            _logger.info(f'   📸 Photo size: {len(delivery_photo) if delivery_photo else 0} bytes')
            _logger.info(f'   ✍️  Signature size: {len(receiver_signature) if receiver_signature else 0} bytes')
            _logger.info(f'   👤 Receiver: {receiver_name} ({receiver_position or "-"}) เซ็นแทน={bool(signed_by_self)}')
            _logger.info(f'   🕐 Delivery Time (planned_end_date_t): {planned_end_date_t} (type: {type(planned_end_date_t).__name__})')
            _logger.info(f'   🎨 Watermark - Time: {delivery_timestamp}')
            _logger.info(f'   🎨 Watermark - Lat: {delivery_latitude}, Lng: {delivery_longitude}')
            
            if not booking_id:
                return {'success': False, 'message': 'Booking ID required'}
            
            # ดึง booking
            booking = request.env['vehicle.booking'].browse(booking_id)
            if not booking.exists():
                _logger.error(f'❌ Booking {booking_id} not found')
                return {'success': False, 'message': 'Booking not found'}

            # คำสั่งนี้มาจากแอปคนขับ — action_done() ที่เรียกต่อจากนี้จะได้
            # สร้างประวัติการจัดส่งเป็นแหล่งที่มา App ไม่ใช่ Odoo
            booking = booking.with_context(npd_from_driver_app=True)
            
            # 🔹 ขั้นที่ 1: บันทึกรูปและลายเซ็น
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.info('🔹 [Step 1] Saving delivery photos and signatures...')
            update_vals = {
                'delivery_photo': delivery_photo,
                'receiver_signature': receiver_signature,
                'receiver_name': receiver_name,
                'signed_by_self': bool(signed_by_self),
            }
            # แอปรุ่นเก่ายังไม่ส่งตำแหน่งมา ถ้าเขียนทับด้วย False ข้อมูลเดิมจะหาย
            if receiver_position:
                update_vals['receiver_position'] = receiver_position
            
            # ✅ บันทึกเวลาส่งจริง
            if planned_end_date_t:
                update_vals['planned_end_date_t'] = planned_end_date_t
                _logger.info(f'✅ [Step 1] Recording actual delivery time: {planned_end_date_t}')
            
            # เพิ่มข้อมูลลายน้ำ GPS
            if delivery_timestamp:
                update_vals['delivery_timestamp'] = delivery_timestamp
            
            if delivery_latitude is not None:
                update_vals['delivery_latitude'] = delivery_latitude
            
            if delivery_longitude is not None:
                update_vals['delivery_longitude'] = delivery_longitude
            
            # อัพเดท booking ด้วยข้อมูลรูปและลายเซ็น
            booking.write(update_vals)

            # เก็บรูปทุกใบไว้เป็นไฟล์แนบ ฟิลด์ delivery_photo เดิมเก็บได้ใบเดียว
            all_photos = ([delivery_photo] if delivery_photo else []) + list(delivery_photos)
            if all_photos:
                saved = booking._npd_store_photos(
                    'delivery_photo_ids', all_photos, 'หลักฐานการส่ง')
                _logger.info('✅ [Step 1] เก็บรูปหลักฐานการส่ง %d ใบ', saved)
            
            _logger.info(f'✅ [Step 1] Delivery photos and signatures saved')
            _logger.info(f'   🎨 Watermark data saved:')
            _logger.info(f'      - delivery_timestamp: {delivery_timestamp}')
            _logger.info(f'      - delivery_latitude: {delivery_latitude}')
            _logger.info(f'      - delivery_longitude: {delivery_longitude}')
            
            # 🔹 ขั้นที่ 2: เรียก action_done() เพื่อ:
            #   1. ปล่อยรถเป็น 'available'
            #   2. สร้างประวัติการจัดส่ง
            #   3. Log ข้อมูลครบ
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.info('🔹 [Step 2] Calling action_done() to finalize delivery...')
            
            # ✅ เรียก action_done()
            booking.action_done()
            
            _logger.info('✅ [Step 2] action_done() completed successfully')
            _logger.info(f'   🚚 Vehicle status: {booking.vehicle_id.vehicle_check_status if booking.vehicle_id else "N/A"}')
            _logger.info(f'   📊 Booking state: {booking.state}')
            _logger.info(f'   📍 Tracking status: {booking.tracking_status}')
            
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.info('✅ [Complete Delivery] DELIVERY COMPLETED SUCCESSFULLY!')
            _logger.info(f'   📦 Booking: {booking.name}')
            _logger.info(f'   ✅ Vehicle released as available')
            _logger.info(f'   ✅ Delivery history created')
            _logger.info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            
            return {
                'success': True,
                'message': 'ส่งของสำเร็จ',
                'booking_name': booking.name,
                'delivery_timestamp': delivery_timestamp,
                'delivery_latitude': delivery_latitude,
                'delivery_longitude': delivery_longitude,
                'vehicle_released': True,
                'delivery_history_created': True,
            }
            
        except Exception as e:
            _logger.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            _logger.error(f'❌ Error completing delivery: {str(e)}')
            import traceback
            _logger.error(f'   Traceback: {traceback.format_exc()}')
            _logger.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
            return {
                'success': False,
                'message': f'Error: {str(e)}',
            }
