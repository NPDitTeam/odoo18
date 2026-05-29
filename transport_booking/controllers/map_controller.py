# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

GOOGLE_API_KEY = "AIzaSyCHKkMOyDdI29v52SULcRx_OcB3i-MD7lw"


class MapController(http.Controller):

    @http.route('/booking/map/<int:booking_id>', type='http', auth='user')
    def show_booking_map(self, booking_id, **kwargs):
        """แสดงแผนที่เส้นทาง"""

        booking = request.env['vehicle.booking'].browse(booking_id)

        if not booking.exists():
            return request.render('transport_booking.map_error', {
                'error': 'ไม่พบข้อมูลการจอง'
            })

        if not booking.pickup_location or not booking.destination:
            return request.render('transport_booking.map_error', {
                'error': 'กรุณากรอกสถานที่รับสินค้าและปลายทาง'
            })

        # ✅ Validate API key
        if not GOOGLE_API_KEY:
            return request.render('transport_booking.map_error', {
                'error': 'ไม่มี Google API Key โปรดติดต่อ Admin'
            })

        return request.render('transport_booking.map_view', {
            'booking': booking,
            'api_key': GOOGLE_API_KEY,
            'origin': booking.pickup_location.replace('\n', ' ').strip(),
            'destination': booking.destination.replace('\n', ' ').strip(),
        })