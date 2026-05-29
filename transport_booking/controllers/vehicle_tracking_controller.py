from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class VehicleTrackingController(http.Controller):
    
    @http.route('/api/tracking/update_location', type='json', auth='public', methods=['POST'], csrf=False)
    def update_location(self, **kwargs):
        """API สำหรับอัปเดตตำแหน่งจากแอป"""
        try:
            # ✅ รองรับทั้ง 2 แบบ: params object หรือ direct fields
            data = request.jsonrequest or {}
            
            # ลองดึง booking_id จาก 'params' ก่อน, ถ้าไม่ได้ให้ดึงจาก root
            booking_id = data.get('params', {}).get('booking_id') or data.get('booking_id')
            latitude = data.get('params', {}).get('latitude') or data.get('latitude')
            longitude = data.get('params', {}).get('longitude') or data.get('longitude')
            
            if not all([booking_id, latitude, longitude]):
                return {
                    'success': False,
                    'error': 'Missing required parameters: booking_id, latitude, longitude',
                    'received': {
                        'booking_id': booking_id,
                        'latitude': latitude,
                        'longitude': longitude,
                    }
                }
            
            # ตรวจสอบ booking
            booking = request.env['vehicle.booking'].sudo().browse(int(booking_id))
            if not booking.exists():
                return {
                    'success': False,
                    'error': f'Booking {booking_id} not found'
                }
            
            # ✅ อัพเดท latitude/longitude ใน booking โดยตรง
            booking.sudo().write({
                'latitude': float(latitude),
                'longitude': float(longitude),
            })
            
            # สร้างจุด tracking history
            tracking_vals = {
                'booking_id': int(booking_id),
                'latitude': float(latitude),
                'longitude': float(longitude),
                'accuracy': data.get('params', {}).get('accuracy') or data.get('accuracy', 0.0),
                'speed': data.get('params', {}).get('speed') or data.get('speed', 0.0),
                'heading': data.get('params', {}).get('heading') or data.get('heading', 0.0),
                'altitude': data.get('params', {}).get('altitude') or data.get('altitude', 0.0),
                'battery_level': data.get('params', {}).get('battery_level') or data.get('battery_level', 0.0),
                'address': data.get('params', {}).get('address') or data.get('address', ''),
            }
            
            tracking = request.env['vehicle.tracking'].sudo().create(tracking_vals)
            
            _logger.info(f"✅ [API] Location updated for booking {booking_id}: {latitude}, {longitude}")
            
            return {
                'success': True,
                'message': 'อัพเดทตำแหน่งสำเร็จ',
                'booking_id': int(booking_id),
                'tracking_id': tracking.id,
            }
            
        except Exception as e:
            _logger.error(f"❌ Error updating location: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
    
    @http.route('/api/tracking/get_latest', type='json', auth='user', methods=['POST'], csrf=False)
    def get_latest_location(self, **kwargs):
        """ดึงตำแหน่งล่าสุดของ booking"""
        try:
            params = request.jsonrequest.get('params', {})
            booking_id = params.get('booking_id')
            
            if not booking_id:
                return {
                    'success': False,
                    'error': 'Missing booking_id'
                }
            
            location = request.env['vehicle.tracking'].sudo().get_latest_location(booking_id)
            
            return {
                'success': True,
                'data': location
            }
            
        except Exception as e:
            _logger.error(f"Error getting latest location: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/api/tracking/get_history', type='json', auth='user', methods=['POST'], csrf=False)
    def get_tracking_history(self, **kwargs):
        """ดึงประวัติการเคลื่อนที่"""
        try:
            params = request.jsonrequest.get('params', {})
            booking_id = params.get('booking_id')
            hours = params.get('hours', 24)
            
            if not booking_id:
                return {
                    'success': False,
                    'error': 'Missing booking_id'
                }
            
            history = request.env['vehicle.tracking'].sudo().get_tracking_history(booking_id, hours)
            
            return {
                'success': True,
                'data': history,
                'count': len(history)
            }
            
        except Exception as e:
            _logger.error(f"Error getting tracking history: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/api/tracking/get_settings', type='json', auth='user', methods=['POST'], csrf=False)
    def get_tracking_settings(self, **kwargs):
        """ดึงการตั้งค่าการติดตามของ user"""
        try:
            user_id = request.env.user.id
            # ใช้ tracking.settings
            settings = request.env['tracking.settings'].sudo().get_user_settings(user_id)
            
            return {
                'success': True,
                'data': settings
            }
            
        except Exception as e:
            _logger.error(f"Error getting tracking settings: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/api/tracking/update_settings', type='json', auth='user', methods=['POST'], csrf=False)
    def update_tracking_settings(self, **kwargs):
        """อัปเดตการตั้งค่าการติดตาม"""
        try:
            params = request.jsonrequest.get('params', {})
            user_id = request.env.user.id
            
            # ดึงหรือสร้าง settings สำหรับ tracking.settings
            settings = request.env['tracking.settings'].sudo().search([
                ('user_id', '=', user_id)
            ], limit=1)
            
            if not settings:
                settings = request.env['tracking.settings'].sudo().create({
                    'user_id': user_id
                })
            
            # อัปเดตค่า - ใช้ fields จาก tracking.settings
            update_vals = {}
            allowed_fields = [
                'tracking_enabled',
                'tracking_interval',
                'high_accuracy',
                'notify_on_arrival',
                'notify_on_delay',
                'notify_off_route',
                'off_route_distance',
                'show_speed',
                'show_route',
                'map_type',
                'save_history',
                'history_retention_days'
            ]
            
            for field in allowed_fields:
                if field in params:
                    update_vals[field] = params[field]
            
            if update_vals:
                settings.write(update_vals)
            
            return {
                'success': True,
                'message': 'Settings updated successfully',
                'data': settings.get_user_settings(user_id)
            }
            
        except Exception as e:
            _logger.error(f"Error updating tracking settings: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/api/tracking/get_active_vehicles', type='json', auth='user', methods=['POST'], csrf=False)
    def get_active_vehicles(self, **kwargs):
        """ดึงรายการรถที่กำลังเคลื่อนที่"""
        try:
            # ค้นหา bookings ที่กำลังทำงาน
            active_bookings = request.env['vehicle.booking'].sudo().search([
                ('state', 'in', ['in_transit', 'at_destination'])
            ])
            
            result = []
            for booking in active_bookings:
                # ดึงตำแหน่งล่าสุด
                latest = request.env['vehicle.tracking'].sudo().get_latest_location(booking.id)
                
                if latest:
                    result.append({
                        'booking_id': booking.id,
                        'booking_name': booking.name,
                        'vehicle_id': booking.vehicle_id.id if booking.vehicle_id else None,
                        'vehicle_name': booking.vehicle_id.name if booking.vehicle_id else '',
                        'driver_id': booking.driver_id.id if booking.driver_id else None,
                        'driver_name': booking.driver_id.name if booking.driver_id else '',
                        'state': booking.state,
                        'location': latest
                    })
            
            return {
                'success': True,
                'data': result,
                'count': len(result)
            }
            
        except Exception as e:
            _logger.error(f"Error getting active vehicles: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
