# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class VehicleBookingAPI(http.Controller):

    # ==========================================
    # POST /api/vehicle-booking
    # ดึงข้อมูล vehicle.booking (เฉพาะ state=done)
    #
    # Body (JSON-RPC):
    # {
    #     "jsonrpc": "2.0",
    #     "method": "call",
    #     "params": {
    #         "month": 1,
    #         "year": 2026,
    #         "driver": "สมชาย",
    #         "limit": 100,
    #         "offset": 0
    #     }
    # }
    # ==========================================
    @http.route('/api/vehicle-booking', type='json', auth='user',
                methods=['POST'], csrf=False)
    def get_vehicle_bookings(self, **kwargs):
        try:
            # เงื่อนไขเริ่มต้น: เฉพาะสถานะเสร็จสิ้น (done)
            domain = [('state', '=', 'done')]

            # --- กรองตามเดือน/ปี ของ planned_start_date_t (วันเวลาออกเดินทางจริง) ---
            month = kwargs.get('month')
            year = kwargs.get('year')

            if month and year:
                month = int(month)
                year = int(year)
                date_start = f'{year}-{month:02d}-01 00:00:00'
                if month == 12:
                    date_end = f'{year + 1}-01-01 00:00:00'
                else:
                    date_end = f'{year}-{month + 1:02d}-01 00:00:00'
                domain += [
                    ('planned_start_date_t', '>=', date_start),
                    ('planned_start_date_t', '<', date_end),
                ]
            elif year:
                year = int(year)
                domain += [
                    ('planned_start_date_t', '>=', f'{year}-01-01 00:00:00'),
                    ('planned_start_date_t', '<', f'{year + 1}-01-01 00:00:00'),
                ]
            elif month:
                month = int(month)
                from datetime import datetime
                current_year = datetime.now().year
                date_start = f'{current_year}-{month:02d}-01 00:00:00'
                if month == 12:
                    date_end = f'{current_year + 1}-01-01 00:00:00'
                else:
                    date_end = f'{current_year}-{month + 1:02d}-01 00:00:00'
                domain += [
                    ('planned_start_date_t', '>=', date_start),
                    ('planned_start_date_t', '<', date_end),
                ]

            # --- กรองตามชื่อคนขับ ---
            driver = kwargs.get('driver')
            if driver:
                domain += [('driver_id.name', 'ilike', driver)]

            # --- limit / offset ---
            limit = int(kwargs.get('limit', 100))
            offset = int(kwargs.get('offset', 0))

            bookings = request.env['vehicle.booking'].sudo().search(
                domain, limit=limit, offset=offset, order='planned_start_date_t desc'
            )
            total_count = request.env['vehicle.booking'].sudo().search_count(domain)

            data = []
            for b in bookings:
                month_val = False
                year_val = False
                planned_start_str = False
                if b.planned_start_date_t:
                    planned_start_str = b.planned_start_date_t.strftime('%Y-%m-%d %H:%M:%S')
                    month_val = b.planned_start_date_t.month
                    year_val = b.planned_start_date_t.year

                data.append({
                    'id': b.id,
                    'name': b.name or '',
                    'travel_expenses': b.travel_expenses or 0.0,
                    'daily_allowance': b.daily_allowance or 0.0,
                    'driver_id': b.driver_id.id if b.driver_id else False,
                    'driver_name': b.driver_id.name if b.driver_id else '',
                    'planned_start_date_t': planned_start_str,
                    'month': month_val,
                    'year': year_val,
                    'state': b.state or '',
                })

            return {
                'status': 'success',
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'count': len(data),
                'data': data,
            }

        except Exception as e:
            _logger.error("API /api/vehicle-booking error: %s", str(e))
            return {
                'status': 'error',
                'message': str(e),
            }

    # ==========================================
    # POST /api/vehicle-booking/detail
    # ดึงข้อมูลรายการเดียว (เฉพาะ state=done)
    #
    # Body (JSON-RPC):
    # {
    #     "jsonrpc": "2.0",
    #     "method": "call",
    #     "params": {
    #         "booking_id": 5
    #     }
    # }
    # ==========================================
    @http.route('/api/vehicle-booking/detail', type='json', auth='user',
                methods=['POST'], csrf=False)
    def get_vehicle_booking_detail(self, **kwargs):
        try:
            booking_id = kwargs.get('booking_id')
            if not booking_id:
                return {
                    'status': 'error',
                    'message': 'Parameter "booking_id" is required',
                }

            booking = request.env['vehicle.booking'].sudo().browse(int(booking_id))
            if not booking.exists():
                return {
                    'status': 'error',
                    'message': f'Booking ID {booking_id} not found',
                }

            # เฉพาะสถานะเสร็จสิ้น (done) เท่านั้น
            if booking.state != 'done':
                return {
                    'status': 'error',
                    'message': f'Booking ID {booking_id} is not completed (state: {booking.state})',
                }

            month_val = False
            year_val = False
            planned_start_str = False
            if booking.planned_start_date_t:
                planned_start_str = booking.planned_start_date_t.strftime('%Y-%m-%d %H:%M:%S')
                month_val = booking.planned_start_date_t.month
                year_val = booking.planned_start_date_t.year

            return {
                'status': 'success',
                'data': {
                    'id': booking.id,
                    'name': booking.name or '',
                    'travel_expenses': booking.travel_expenses or 0.0,
                    'daily_allowance': booking.daily_allowance or 0.0,
                    'driver_id': booking.driver_id.id if booking.driver_id else False,
                    'driver_name': booking.driver_id.name if booking.driver_id else '',
                    'planned_start_date_t': planned_start_str,
                    'month': month_val,
                    'year': year_val,
                    'state': booking.state or '',
                },
            }

        except Exception as e:
            _logger.error("API /api/vehicle-booking/detail error: %s", str(e))
            return {
                'status': 'error',
                'message': str(e),
            }

    # ==========================================
    # POST /api/vehicle-booking/summary
    # สรุปรวมตามเดือน/ปี (เฉพาะ state=done)
    #
    # Body (JSON-RPC):
    # {
    #     "jsonrpc": "2.0",
    #     "method": "call",
    #     "params": {
    #         "year": 2026
    #     }
    # }
    # ==========================================
    @http.route('/api/vehicle-booking/summary', type='json', auth='user',
                methods=['POST'], csrf=False)
    def get_vehicle_booking_summary(self, **kwargs):
        try:
            year = kwargs.get('year')
            if not year:
                return {
                    'status': 'error',
                    'message': 'Parameter "year" is required',
                }

            year = int(year)
            domain = [
                ('state', '=', 'done'),
                ('planned_start_date_t', '>=', f'{year}-01-01 00:00:00'),
                ('planned_start_date_t', '<', f'{year + 1}-01-01 00:00:00'),
            ]

            bookings = request.env['vehicle.booking'].sudo().search(domain)

            monthly_summary = {}
            for b in bookings:
                if not b.planned_start_date_t:
                    continue
                m = b.planned_start_date_t.month
                if m not in monthly_summary:
                    monthly_summary[m] = {
                        'month': m,
                        'year': year,
                        'total_travel_expenses': 0.0,
                        'total_daily_allowance': 0.0,
                        'booking_count': 0,
                        'drivers': [],
                    }
                monthly_summary[m]['total_travel_expenses'] += (b.travel_expenses or 0.0)
                monthly_summary[m]['total_daily_allowance'] += (b.daily_allowance or 0.0)
                monthly_summary[m]['booking_count'] += 1

                driver_name = b.driver_id.name if b.driver_id else ''
                if driver_name and driver_name not in monthly_summary[m]['drivers']:
                    monthly_summary[m]['drivers'].append(driver_name)

            summary_list = sorted(monthly_summary.values(), key=lambda x: x['month'])

            return {
                'status': 'success',
                'year': year,
                'data': summary_list,
            }

        except Exception as e:
            _logger.error("API /api/vehicle-booking/summary error: %s", str(e))
            return {
                'status': 'error',
                'message': str(e),
            }
