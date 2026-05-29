# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import uuid
import logging
import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta
import requests

_logger = logging.getLogger(__name__)


class DeliveryRating(models.Model):
    _name = 'delivery.rating'
    _description = 'Customer Delivery Rating / การประเมินการขนส่งโดยลูกค้า'
    _order = 'create_date desc'
    _rec_name = 'booking_id'

    # JWT Configuration
    JWT_SECRET = 'npd-transport-rating-secret-2024-change-this'
    TOKEN_EXPIRY = 7 * 24 * 60 * 60  # 7 วัน

    # ข้อมูลการประเมิน
    booking_id = fields.Many2one('vehicle.booking', string='การจองขนส่ง', 
                                  required=True, ondelete='cascade', index=True)
    driver_id = fields.Many2one('vehicle.driver', string='พนักงานขับรถ',
                                related='booking_id.driver_id', store=True, readonly=True)
    driver_name = fields.Char('ชื่อพนักงาน', related='driver_id.name', store=True, readonly=True)
    
    # Token สำหรับ public URL (เก่า - ยังคง keep ไว้ compatibility)
    rating_token = fields.Char('Rating Token (UUID)', default=lambda self: str(uuid.uuid4()), 
                               required=True, readonly=True, copy=False, index=True, unique=True)
    
    # JWT Token (ใหม่ - ปลอดภัยกว่า)
    jwt_token = fields.Char('JWT Token', readonly=True, copy=False, index=True)
    
    # คะแนนประเมิน
    rating_stars = fields.Selection([
        ('1', '⭐ แย่มาก'),
        ('2', '⭐⭐ แย่'),
        ('3', '⭐⭐⭐ ปานกลาง'),
        ('4', '⭐⭐⭐⭐ ดี'),
        ('5', '⭐⭐⭐⭐⭐ ดีมาก'),
    ], string='คะแนนประเมิน')
    
    rating_value = fields.Integer('คะแนน (1-5)', compute='_compute_rating_value', store=True)
    
    # ความคิดเห็น
    customer_comment = fields.Text('ความคิดเห็นจากลูกค้า')
    
    # วันที่
    rating_date = fields.Datetime('วันที่ประเมิน', readonly=True)
    # หมายเหตุ: ใช้ create_date (field มาตรฐาน) สำหรับวันที่สร้าง Link
    
    # สถานะ
    state = fields.Selection([
        ('pending', 'รอการประเมิน'),
        ('done', 'ประเมินแล้ว'),
        ('expired', 'หมดอายุ'),
    ], string='สถานะ', default='pending', required=True)
    
    # ข้อมูลเพิ่มเติม
    customer_name = fields.Char('ชื่อลูกค้า', related='booking_id.partner_id.name', 
                                 store=True, readonly=True)
    pickup_location = fields.Text('สถานที่รับ', related='booking_id.pickup_location', 
                                   store=True, readonly=True)
    destination = fields.Text('ปลายทาง', related='booking_id.destination', 
                             store=True, readonly=True)
    
    # Public Link
    rating_url = fields.Char('Link ประเมิน', compute='_compute_rating_url', store=False)
    
    # SQL Constraints
    _sql_constraints = [
        ('booking_unique', 'UNIQUE(booking_id)', 
         '⚠️ การจองนี้มี Link ประเมินอยู่แล้ว! ไม่สามารถสร้างซ้ำได้'),
    ]
    
    # ========================================
    # JWT Token Functions (ใหม่)
    # ========================================
    
    def _create_jwt_token(self, booking_id, customer_email=''):
        """
        ✅ สร้าง JWT Token
        """
        issued_at = int(datetime.now().timestamp())
        exp = issued_at + self.TOKEN_EXPIRY
        
        payload = {
            'booking_id': booking_id,
            'customer_email': customer_email,
            'iat': issued_at,
            'exp': exp
        }
        
        # ✅ สร้าง JWT (Header.Payload.Signature)
        header = {'alg': 'HS256', 'typ': 'JWT'}
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        
        # ✅ สร้าง Signature
        message = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            self.JWT_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
        
        jwt_token = f"{message}.{signature_b64}"
        
        _logger.info(f"✅ JWT Token created for booking_id={booking_id}")
        return jwt_token
    
    def _verify_jwt_token(self, token):
        """
        ✅ ตรวจสอบ JWT Token
        """
        try:
            parts = token.split('.')
            if len(parts) != 3:
                _logger.warning(f"❌ Invalid token format: {token[:50]}")
                return None
            
            header_b64, payload_b64, signature_b64 = parts
            
            # ✅ ตรวจสอบ Signature
            message = f"{header_b64}.{payload_b64}"
            signature = hmac.new(
                self.JWT_SECRET.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()
            signature_calc = base64.urlsafe_b64encode(signature).decode().rstrip('=')
            
            if not hmac.compare_digest(signature_b64, signature_calc):
                _logger.warning(f"❌ Token signature invalid")
                return None
            
            # ✅ Decode Payload
            payload_json = base64.urlsafe_b64decode(payload_b64 + '==')
            payload = json.loads(payload_json)
            
            # ✅ ตรวจสอบ Expiration
            if payload['exp'] < int(datetime.now().timestamp()):
                _logger.warning(f"❌ Token expired")
                return None
            
            _logger.info(f"✅ JWT Token verified: booking_id={payload['booking_id']}")
            return payload
        except Exception as e:
            _logger.error(f"❌ Token verification error: {e}")
            return None
    
    @api.depends('rating_stars')
    def _compute_rating_value(self):
        """แปลง rating_stars เป็นตัวเลข"""
        for record in self:
            if record.rating_stars:
                record.rating_value = int(record.rating_stars)
            else:
                record.rating_value = 0
    
    @api.depends('rating_token')
    def _compute_rating_url(self):
        """
        สร้าง Public URL สำหรับการประเมิน
        ✅ HARDCODED: ใช้ production domain เสมอ
        """
        # ✅ Hardcoded production URL
        PRODUCTION_URL = 'https://npdhrms.com'
        
        for record in self:
            if record.rating_token:
                # ✅ FORCE FORMAT: https://npdhrms.com/rating/TOKEN
                record.rating_url = f"{PRODUCTION_URL}/rating/{record.rating_token}"
            else:
                record.rating_url = False
    
    def action_send_rating_link(self):
        """ส่ง Link ประเมินให้ลูกค้า (สำหรับอนาคต - อาจส่งผ่าน SMS/Email)"""
        self.ensure_one()
        # TODO: ส่ง SMS หรือ Email ให้ลูกค้า
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rating Link'),
                'message': _('Link: %s') % self.rating_url,
                'type': 'success',
                'sticky': False,
            }
        }
    
    @api.model
    def submit_rating(self, token, rating_stars, customer_comment=None):
        """
        บันทึกการประเมินจากลูกค้า (เรียกจาก public form)
        ✅ FIX: Allow overwriting previous ratings
        ✅ FIX: ใช้ with_user(False) เพื่อให้ public user บันทึกได้
        """
        try:
            # ✅ ใช้ False user สำหรับ public access
            rating = self.with_user(False).search([
                ('rating_token', '=', token),
            ], limit=1)
            
            if not rating:
                _logger.warning(f"⚠️ Rating submission failed: Invalid token={token}")
                raise ValidationError(_('Invalid rating link'))
            
            # ✅ FIX: Allow update even if already done (allow re-rating)
            if rating.state == 'expired':
                _logger.warning(f"⚠️ Rating submission failed: Link expired for token={token}")
                raise ValidationError(_('This rating link has expired'))
            
            # บันทึกการประเมิน
            rating.write({
                'rating_stars': str(rating_stars),
                'customer_comment': customer_comment or '',
                'rating_date': fields.Datetime.now(),
                'state': 'done',
            })
            
            _logger.info(f"✅ Rating submitted: Booking={rating.booking_id.name}, Stars={rating_stars}, Token={token}")
            
            return {
                'success': True,
                'message': 'ขอบคุณสำหรับการประเมิน',
                'booking_name': rating.booking_id.name,
                'driver_name': rating.driver_name or 'N/A',
            }
        except ValidationError:
            raise
        except Exception as e:
            _logger.error(f"❌ Error in submit_rating: {e}", exc_info=True)
            raise ValidationError(_(f'Error: {str(e)}'))
    
    @api.model
    def get_rating_info(self, token):
        """
        ดึงข้อมูลสำหรับแสดงในหน้าประเมิน (สำหรับ public form)
        ✅ FIX: Removed strict 'pending' state check - allows access even after rating
        ✅ FIX: Better error logging for debugging
        ✅ FIX: ใช้ with_user(False) เพื่อให้ public user เข้าได้
        """
        _logger.info(f"🔍 get_rating_info called with token={token}")
        
        try:
            # ✅ CHANGED: ใช้ False user สำหรับ public access
            rating = self.with_user(False).search([
                ('rating_token', '=', token),
                ('state', '!=', 'expired')  # Only reject if explicitly expired
            ], limit=1)
            
            if not rating:
                _logger.warning(f"⚠️ Rating not found for token={token}")
                return {'error': 'Invalid or expired rating link'}
            
            _logger.info(f"✅ Rating found: Booking={rating.booking_id.name}, State={rating.state}, Token={token}")
            
            return {
                'booking_name': rating.booking_id.name,
                'driver_name': rating.driver_name or 'N/A',
                'pickup_location': rating.pickup_location or 'N/A',
                'destination': rating.destination or 'N/A',
                'customer_name': rating.customer_name or 'N/A',
                'state': rating.state,  # Include state info for frontend
                'rating_id': rating.id,
            }
        except Exception as e:
            _logger.error(f"❌ Error in get_rating_info: {e}", exc_info=True)
            return {'error': str(e)}
    
    def action_mark_expired(self):
        """ทำเครื่องหมายว่าหมดอายุ"""
        for record in self:
            if record.state == 'pending':
                record.state = 'expired'


class VehicleBooking(models.Model):
    _inherit = 'vehicle.booking'
    
    rating_ids = fields.One2many('delivery.rating', 'booking_id', string='การประเมิน')
    rating_count = fields.Integer('จำนวนการประเมิน', compute='_compute_rating_count')
    latest_rating = fields.Float('คะแนนล่าสุด', compute='_compute_latest_rating', store=True)
    
    @api.depends('rating_ids')
    def _compute_rating_count(self):
        for record in self:
            record.rating_count = len(record.rating_ids.filtered(lambda r: r.state == 'done'))
    
    @api.depends('rating_ids.rating_value', 'rating_ids.state')
    def _compute_latest_rating(self):
        for record in self:
            done_ratings = record.rating_ids.filtered(lambda r: r.state == 'done')
            if done_ratings:
                record.latest_rating = done_ratings[0].rating_value
            else:
                record.latest_rating = 0.0
    
    def action_create_rating_link(self):
        """สร้าง Rating Link ใหม่ - เช็คว่ามีอยู่แล้วหรือไม่"""
        self.ensure_one()
        
        # เช็คว่างานเสร็จแล้วหรือยัง
        if self.state != 'done':
            raise ValidationError(_('สามารถสร้าง Rating Link ได้เฉพาะงานที่เสร็จสิ้นแล้ว'))
        
        # เช็คว่ามี Rating Link อยู่แล้วหรือไม่
        existing_rating = self.env['delivery.rating'].search([
            ('booking_id', '=', self.id)
        ], limit=1)
        
        if existing_rating:
            # ถ้ามีแล้ว → เปิด rating เดิม
            return {
                'name': _('📝 Link ประเมินความพึงพอใจ (มีอยู่แล้ว)'),
                'type': 'ir.actions.act_window',
                'res_model': 'delivery.rating',
                'res_id': existing_rating.id,
                'view_mode': 'form',
                'target': 'new',
            }
        else:
            # ถ้ายังไม่มี → เปิดฟอร์มใหม่
            return {
                'name': _('📝 สร้าง Link ประเมินความพึงพอใจ'),
                'type': 'ir.actions.act_window',
                'res_model': 'delivery.rating',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_booking_id': self.id,
                },
            }
    
    def action_view_ratings(self):
        """ดูประวัติการประเมินทั้งหมด"""
        self.ensure_one()
        return {
            'name': _('ประวัติการประเมิน'),
            'type': 'ir.actions.act_window',
            'res_model': 'delivery.rating',
            'view_mode': 'tree,form',
            'domain': [('booking_id', '=', self.id)],
            'context': {'default_booking_id': self.id},
        }
