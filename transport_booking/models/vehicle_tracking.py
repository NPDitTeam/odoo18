from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta


class VehicleTracking(models.Model):
    _name = 'vehicle.tracking'
    _description = 'Vehicle Location Tracking'
    _order = 'timestamp desc'

    booking_id = fields.Many2one('vehicle.booking', string='Booking', required=True, ondelete='cascade', index=True)
    driver_id = fields.Many2one('vehicle.driver', string='Driver', index=True, ondelete='set null')  # ✅ เปลี่ยนจาก required=True, restrict เป็น set null
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle', related='booking_id.vehicle_id', store=True)
    
    latitude = fields.Float('Latitude', required=True, digits=(10, 7))
    longitude = fields.Float('Longitude', required=True, digits=(10, 7))
    accuracy = fields.Float('Accuracy (meters)')
    speed = fields.Float('Speed (km/h)')
    heading = fields.Float('Heading (degrees)')
    altitude = fields.Float('Altitude (meters)')
    
    timestamp = fields.Datetime('Timestamp', required=True, default=fields.Datetime.now, index=True)
    battery_level = fields.Float('Battery Level (%)')
    is_moving = fields.Boolean('Is Moving', compute='_compute_is_moving', store=True)
    
    # เก็บข้อมูลเพิ่มเติม
    address = fields.Char('Address')
    notes = fields.Text('Notes')
    
    @api.depends('speed')
    def _compute_is_moving(self):
        for record in self:
            record.is_moving = record.speed and record.speed > 5.0  # ถือว่าเคลื่อนที่ถ้าเร็วกว่า 5 km/h
    
    @api.model
    def create_tracking_point(self, vals):
        """สร้างจุด tracking ใหม่"""
        return self.create(vals)
    
    @api.model
    def get_latest_location(self, booking_id):
        """ดึงตำแหน่งล่าสุดของ booking"""
        tracking = self.search([
            ('booking_id', '=', booking_id)
        ], limit=1, order='timestamp desc')
        
        if tracking:
            return {
                'latitude': tracking.latitude,
                'longitude': tracking.longitude,
                'timestamp': tracking.timestamp.isoformat() if tracking.timestamp else None,
                'speed': tracking.speed,
                'heading': tracking.heading,
                'is_moving': tracking.is_moving,
                'address': tracking.address,
            }
        return None
    
    @api.model
    def get_tracking_history(self, booking_id, hours=24):
        """ดึงประวัติการเคลื่อนที่ย้อนหลัง"""
        since = datetime.now() - timedelta(hours=hours)
        trackings = self.search([
            ('booking_id', '=', booking_id),
            ('timestamp', '>=', since)
        ], order='timestamp asc')
        
        return [{
            'id': t.id,
            'latitude': t.latitude,
            'longitude': t.longitude,
            'timestamp': t.timestamp.isoformat() if t.timestamp else None,
            'speed': t.speed,
            'heading': t.heading,
            'is_moving': t.is_moving,
            'address': t.address,
        } for t in trackings]
    
    @api.model
    def cleanup_old_tracking(self, days=30):
        """ลบข้อมูล tracking เก่าเกิน X วัน"""
        cutoff_date = datetime.now() - timedelta(days=days)
        old_trackings = self.search([
            ('timestamp', '<', cutoff_date)
        ])
        return old_trackings.unlink()


class TrackingSettings(models.Model):
    _name = 'tracking.settings'
    _description = 'Tracking Settings'
    
    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade', index=True)
    
    # การตั้งค่าการติดตาม
    tracking_enabled = fields.Boolean('เปิดการติดตาม', default=True,
        help='เปิด/ปิดการติดตามตำแหน่ง')
    tracking_interval = fields.Integer('ช่วงเวลาการติดตาม (นาที)', default=5,
        help='ระยะเวลาในการส่งตำแหน่ง (นาที)')
    high_accuracy = fields.Boolean('โหมดความแม่นยำสูง', default=True,
        help='ใช้ GPS ความแม่นยำสูง (กินแบตเตอรี่มากขึ้น)')
    
    # การตั้งค่าการแจ้งเตือน
    notify_on_arrival = fields.Boolean('แจ้งเตือนเมื่อถึงจุดหมาย', default=True,
        help='แจ้งเตือนเมื่อถึงจุดหมาย')
    notify_on_delay = fields.Boolean('แจ้งเตือนเมื่อล่าช้า', default=True,
        help='แจ้งเตือนเมื่อล่าช้า')
    notify_off_route = fields.Boolean('แจ้งเตือนออกนอกเส้นทาง', default=True,
        help='แจ้งเตือนเมื่อรถออกนอกเส้นทาง')
    off_route_distance = fields.Integer('ระยะออกนอกเส้นทาง (เมตร)', default=500,
        help='ระยะห่างจากเส้นทางที่ถือว่าออกนอกเส้นทาง (เมตร)')
    
    # การตั้งค่าการแสดงผล
    show_speed = fields.Boolean('แสดงความเร็ว', default=True,
        help='แสดงความเร็วบนแผนที่')
    show_route = fields.Boolean('แสดงเส้นทาง', default=True,
        help='แสดงเส้นทางที่เดินทางมา')
    map_type = fields.Selection([
        ('roadmap', 'แผนที่ถนน'),
        ('satellite', 'ภาพถ่ายดาวเทียม'),
        ('hybrid', 'แบบผสม'),
        ('terrain', 'แผนที่ภูมิประเทศ'),
    ], string='ประเภทแผนที่', default='roadmap',
        help='ประเภทของแผนที่')
    
    # การตั้งค่าการบันทึก
    save_history = fields.Boolean('บันทึกประวัติ', default=True,
        help='บันทึกประวัติการเคลื่อนที่')
    history_retention_days = fields.Integer('เก็บประวัติ (วัน)', default=30,
        help='เก็บประวัติไว้กี่วัน')
    
    _sql_constraints = [
        ('user_id_unique', 'UNIQUE(user_id)', 'Each user can have only one tracking settings record!')
    ]
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to prevent duplicate settings per user"""
        for vals in vals_list:
            user_id = vals.get('user_id')
            if user_id:
                # Check if settings already exist for this user
                existing = self.search([('user_id', '=', user_id)], limit=1)
                if existing:
                    # Update existing record instead of creating new one
                    existing.write(vals)
                    return existing
        return super(TrackingSettings, self).create(vals_list)
    
    def write(self, vals):
        """Override write to ensure user_id doesn't change"""
        if 'user_id' in vals and self.user_id:
            # Don't allow changing user_id if already set
            if vals['user_id'] != self.user_id.id:
                raise ValidationError('Cannot change user for tracking settings!')
        return super(TrackingSettings, self).write(vals)
    
    @api.model
    def get_or_create_settings(self, user_id):
        """ดึงหรือสร้างการตั้งค่าสำหรับ user"""
        settings = self.search([('user_id', '=', user_id)], limit=1)
        if not settings:
            settings = self.create({'user_id': user_id})
        return settings
    
    @api.model
    def get_user_settings(self, user_id):
        """ดึงการตั้งค่าของ user"""
        settings = self.get_or_create_settings(user_id)
        return {
            'tracking_enabled': settings.tracking_enabled,
            'tracking_interval': settings.tracking_interval,
            'high_accuracy': settings.high_accuracy,
            'notify_on_arrival': settings.notify_on_arrival,
            'notify_on_delay': settings.notify_on_delay,
            'notify_off_route': settings.notify_off_route,
            'off_route_distance': settings.off_route_distance,
            'show_speed': settings.show_speed,
            'show_route': settings.show_route,
            'map_type': settings.map_type,
            'save_history': settings.save_history,
            'history_retention_days': settings.history_retention_days,
        }
