# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class RatingController(http.Controller):
    
    @http.route('/rating/<token>', type='http', auth='public', website=True, csrf=False)
    def rating_form(self, token, **kwargs):
        """
        แสดงหน้าฟอร์มประเมินความพึงพอใจ (สำหรับลูกค้า)
        FIX: ลบ <string:> เพื่อให้ token ทำงานได้อย่างถูกต้อง
        """
        try:
            _logger.info(f"🔍 Rating form requested with token: {token}")
            
            # ดึงข้อมูล rating
            rating_info = request.env['delivery.rating'].sudo().get_rating_info(token)
            
            if 'error' in rating_info:
                _logger.warning(f"⚠️ Rating not found or expired: {token}")
                return request.render('transport_booking.rating_expired_template')
            
            _logger.info(f"✅ Rating form loaded successfully for booking: {rating_info.get('booking_name')}")
            
            # แสดงฟอร์มประเมิน
            return request.render('transport_booking.rating_form_template', {
                'rating_info': rating_info,
                'token': token,
            })
            
        except Exception as e:
            _logger.error(f"❌ Error loading rating form: {e}", exc_info=True)
            return request.render('transport_booking.rating_error_template')
    
    @http.route('/rating/submit', type='json', auth='public', methods=['POST'], csrf=False)
    def rating_submit(self, token, rating_stars, customer_comment=None, **kwargs):
        """
        บันทึกการประเมิน (เรียกจาก JavaScript)
        FIX: เพิ่ม logging และ error handling
        """
        try:
            _logger.info(f"📝 Submitting rating - Token: {token}, Stars: {rating_stars}")
            
            result = request.env['delivery.rating'].sudo().submit_rating(
                token=token,
                rating_stars=int(rating_stars),
                customer_comment=customer_comment
            )
            
            _logger.info(f"✅ Rating submitted successfully: {result}")
            return result
            
        except Exception as e:
            _logger.error(f"❌ Error submitting rating: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/rating/success', type='http', auth='public', website=True)
    def rating_success(self, **kwargs):
        """หน้าขอบคุณหลังประเมินเสร็จ"""
        return request.render('transport_booking.rating_success_template')
