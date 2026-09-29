# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class DeliveryHistory(models.Model):
    """โมเดลสำหรับเก็บประวัติการจัดส่งที่เสร็จสิ้นแล้ว"""
    _name = 'delivery.history'
    _description = 'Delivery History / ประวัติการจัดส่ง'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'completion_date desc'

    # ข้อมูลพื้นฐาน
    name = fields.Char('เลขที่จอง', required=True, tracking=True, index=True)
    booking_id = fields.Many2one('vehicle.booking', string='การจองที่เกี่ยวข้อง',
                                 ondelete='set null', index=True)

    # ข้อมูลการจัดส่ง
    partner_id = fields.Many2one('res.partner', string='ลูกค้า', tracking=True)
    partner_name = fields.Char('ชื่อลูกค้า', tracking=True)

    # เส้นทาง
    pickup_location = fields.Text('ต้นทาง', tracking=True)
    destination = fields.Text('ปลายทาง', tracking=True)
    distance_km = fields.Float('ระยะทาง (กม.)', digits=(10, 3))
    total_weight_order = fields.Float('น้ำหนักรวม (กก.)', digits=(10, 2),
                                      help='น้ำหนักรวมจากรายการสินค้า')

    # พนักงานและรถ
    driver_id = fields.Many2one('vehicle.driver', string='คนขับ', tracking=True)
    driver_name = fields.Char('ชื่อคนขับ', tracking=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='รถ', tracking=True)
    vehicle_name = fields.Char('ทะเบียนรถ', tracking=True)

    # ค่าใช้จ่าย
    shipping_cost = fields.Float('ค่าขนส่ง', digits=(10, 2), tracking=True)
    travel_expenses = fields.Float('ค่าเที่ยว', digits=(10, 2), tracking=True, help='ค่าเที่ยวสำหรับคนขับ')
    daily_allowance = fields.Float('ค่าเบี้ยเลี้ยง', digits=(10, 2), tracking=True, help='ค่าเบี้ยเลี้ยงสำหรับคนขับ')
    currency_id = fields.Many2one('res.currency', string='สกุลเงิน',
                                  default=lambda self: self.env.company.currency_id)

    # เวลาการทำงาน
    planned_start_date = fields.Datetime('วันเวลาที่วางแผนเริ่ม', tracking=True)
    planned_start_date_t = fields.Datetime('เวลาออกเดินทางจริง', tracking=True)
    actual_pickup_time = fields.Datetime('เวลารับสินค้าจริง', tracking=True)
    actual_delivery_time = fields.Datetime('เวลาส่งถึงจริง', tracking=True)
    planned_end_date = fields.Datetime('วันเวลาที่วางแผนส่งถึง', tracking=True)
    planned_end_date_t = fields.Datetime('เวลาส่งจริง (Thailand)', tracking=True)
    completion_date = fields.Datetime('วันที่เสร็จสิ้น', default=fields.Datetime.now,
                                     required=True, tracking=True, index=True)

    # ระยะเวลา (คำนวณอัตโนมัติ)
    duration_hours = fields.Float('ระยะเวลาจัดส่ง (ชั่วโมง)', compute='_compute_duration',
                                  store=True, digits=(10, 2))

    # หลักฐาน
    pickup_photo = fields.Binary('รูปถ่ายสินค้าก่อนขนส่ง', attachment=True)
    delivery_photo = fields.Binary('รูปถ่ายหลักฐานการส่ง', attachment=True)
    receiver_name = fields.Char('ชื่อผู้รับ', tracking=True)
    receiver_position = fields.Char('ตำแหน่งผู้รับ', tracking=True)
    signed_by_self = fields.Boolean('เซ็นรับแทน (ไม่เจอลูกค้า)', tracking=True)
    receiver_signature = fields.Binary('ลายเซ็นผู้รับ', attachment=True)

    # พิกัด GPS
    pickup_latitude = fields.Float('Pickup Latitude', digits=(10, 7))
    pickup_longitude = fields.Float('Pickup Longitude', digits=(10, 7))
    destination_latitude = fields.Float('Destination Latitude', digits=(10, 7))
    destination_longitude = fields.Float('Destination Longitude', digits=(10, 7))

    # หมายเหตุ
    note = fields.Html('หมายเหตุ')
    tracking_notes = fields.Text('บันทึกการติดตาม')

    # สถานะ
    state = fields.Selection([
        ('completed', '✅ เสร็จสิ้น'),
        ('cancelled', '❌ ยกเลิก'),
    ], string='สถานะ', default='completed', required=True, tracking=True)

    # แหล่งที่มา
    source = fields.Selection([
        ('app', '📱 App'),
        ('odoo', '🖥️ Odoo'),
    ], string='แหล่งที่มา', default='app', required=True, tracking=True)

    @api.depends('actual_pickup_time', 'actual_delivery_time')
    def _compute_duration(self):
        """คำนวณระยะเวลาจัดส่ง (ชั่วโมง)"""
        for record in self:
            if record.actual_pickup_time and record.actual_delivery_time:
                delta = record.actual_delivery_time - record.actual_pickup_time
                record.duration_hours = delta.total_seconds() / 3600.0
            else:
                record.duration_hours = 0.0

    @api.model
    def create_from_booking(self, booking, source='app'):
        """สร้างประวัติจากการจองที่เสร็จสิ้น
        Args:
            booking: vehicle.booking record
            source: 'app' (จากแอป) หรือ 'odoo' (จาก Odoo)
        """
        if not booking:
            return False

        # ✅ ถ้ามี receiver_name หรือ actual_pickup_time แสดงว่าข้อมูลมาจากแอป
        if booking.receiver_name or booking.actual_pickup_time:
            source = 'app'
            _logger.info(f"📱 Detected app data (receiver_name or actual_pickup_time exists), setting source='app'")

        _logger.info(f"📜 Creating delivery history from booking: {booking.name} (source: {source})")

        try:
            history_vals = {
                'name': booking.name,
                'booking_id': booking.id,
                'partner_id': booking.partner_id.id if booking.partner_id else False,
                'partner_name': booking.partner_id.name if booking.partner_id else '',
                'pickup_location': booking.pickup_location,
                'destination': booking.destination,
                'distance_km': booking.distance_km,
                'total_weight_order': booking.total_weight_order,
                'driver_id': booking.driver_id.id if booking.driver_id else False,
                'driver_name': booking.driver_id.name if booking.driver_id else '',
                'vehicle_id': booking.vehicle_id.id if booking.vehicle_id else False,
                'vehicle_name': booking.vehicle_id.license_plate if booking.vehicle_id else '',
                'shipping_cost': booking.shipping_cost,
                'travel_expenses': float(booking.travel_expenses) if booking.travel_expenses else 0.0,
                'daily_allowance': float(booking.daily_allowance) if booking.daily_allowance else 0.0,
                'currency_id': booking.currency_id.id if booking.currency_id else False,
                'planned_start_date': booking.planned_start_date,
                'planned_start_date_t': booking.planned_start_date_t if booking.planned_start_date_t else booking.actual_pickup_time,
                'actual_pickup_time': booking.actual_pickup_time,
                'actual_delivery_time': booking.actual_delivery_time,
                'planned_end_date': booking.planned_end_date,
                'planned_end_date_t': booking.planned_end_date_t if booking.planned_end_date_t else booking.actual_delivery_time,
                'completion_date': fields.Datetime.now(),
                'pickup_photo': booking.pickup_photo,
                'delivery_photo': booking.delivery_photo,
                'receiver_name': booking.receiver_name,
                'receiver_position': booking.receiver_position,
                'signed_by_self': booking.signed_by_self,
                'receiver_signature': booking.receiver_signature,
                'pickup_latitude': booking.pickup_latitude,
                'pickup_longitude': booking.pickup_longitude,
                'destination_latitude': booking.destination_latitude,
                'destination_longitude': booking.destination_longitude,
                'note': booking.note,
                'tracking_notes': booking.tracking_notes,
                'state': 'completed' if booking.state == 'done' else 'cancelled',
                'source': source,
            }

            history = self.create(history_vals)
            _logger.info(f"✅ Created delivery history: {history.name} (ID: {history.id})")

            return history

        except Exception as e:
            _logger.error(f"❌ Error creating delivery history: {str(e)}")
            _logger.error(f"📋 Traceback: {e.__class__.__name__}")
            import traceback
            _logger.error(traceback.format_exc())
            return False

    def action_view_booking(self):
        """ดูการจองที่เกี่ยวข้อง"""
        self.ensure_one()
        if not self.booking_id:
            raise ValidationError('ไม่พบข้อมูลการจองที่เกี่ยวข้อง')

        return {
            'name': f'การจอง: {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'vehicle.booking',
            'view_mode': 'form',
            'res_id': self.booking_id.id,
            'target': 'current',
        }

    def action_view_map(self):
        """ดูแผนที่เส้นทาง"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/delivery/history/map/{self.id}',
            'target': 'new',
        }
