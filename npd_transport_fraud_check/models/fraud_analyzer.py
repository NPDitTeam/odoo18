# -*- coding: utf-8 -*-
"""ตัวตรวจทุจริตการจัดส่ง

หลักคิด
    1. "กฎ" ตรวจทุกเที่ยวที่ปิดงาน — เร็ว ไม่เสียค่า AI และตรวจย้อนหลังได้เป็นพัน ๆ ใบ
       กฎเทียบกับ "พฤติกรรมของกลุ่ม" (เพื่อนร่วมสาขา / ค่ากลางของประเภทการจัดส่งนั้น)
       ไม่ได้ตั้งตัวเลขตายตัว เพราะค่าเที่ยวแต่ละสาขา/ระยะทางต่างกัน
    2. ใบที่กฎจับได้ค่อยส่งให้ AI อ่านข้อมูลประกอบแล้วสรุปเป็นภาษาไทย (ทำเป็นรอบด้วย cron
       ไม่ทำตอนคนขับกดปิดงาน เพราะจะทำให้แอปค้างรอ)

ที่มาของข้อมูลที่ใช้ตรวจ
    vehicle.booking : travel_expenses (ค่าเที่ยว), daily_allowance (เบี้ยเลี้ยง),
                      distance_km, delivery_date, branch_id, driver_id,
                      delivery_source/source (app หรือ odoo), no_app_done_reason,
                      actual_pickup_time / actual_delivery_time, is_concurrent_booking
    transport.order : delivery_type (ประเภทการจัดส่งที่ตั้งไว้ฝั่ง Odoo 14),
                      trip_allowance, daily_allowance, use_special_delivery_zero,
                      shipping_cost
"""
import json
import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.tools.misc import html_escape

from . import fraud_rules
from .fraud_rules import DELIVERY_TYPE_LABELS

_logger = logging.getLogger(__name__)

# เริ่มเก็บสถิติย้อนหลังตั้งแต่เดือน 6 (ตามที่ผู้ใช้ระบุ 16 ก.ย. 2569)
BACKFILL_START = date(2026, 6, 1)

# หน้าต่างเวลาที่ใช้เทียบพฤติกรรมกลุ่ม (วัน)
PEER_WINDOW_DAYS = 120

# คะแนนรวมที่ถือว่าน่าสงสัย
SCORE_WATCH = 20
SCORE_HIGH = 40
# ส่งให้ AI อธิบายเมื่อคะแนนถึงเท่านี้
SCORE_AI = 20

def _fmt(value):
    return '{:,.2f}'.format(value or 0.0)


class NpdTransportFraudAnalyzer(models.AbstractModel):
    _name = 'npd.transport.fraud.analyzer'
    _description = 'ตัวตรวจทุจริตการจัดส่ง'

    # ------------------------------------------------------------------
    # ค่ากลางของกลุ่ม (คิดด้วย SQL ครั้งเดียวต่อรอบ แล้วเก็บไว้ใช้ซ้ำ)
    # ------------------------------------------------------------------
    @api.model
    def _peer_stats(self, ref_date=None):
        """สถิติที่ใช้เทียบ: สัดส่วนประเภทการจัดส่งของคนขับ/สาขา และค่ากลางค่าเที่ยว"""
        ref_date = ref_date or fields.Date.context_today(self)
        date_from = ref_date - timedelta(days=PEER_WINDOW_DAYS)
        cr = self.env.cr

        cr.execute("""
            SELECT b.driver_id, b.branch_id,
                   COUNT(*) AS trips,
                   COUNT(*) FILTER (WHERE o.delivery_type = 'customer') AS customer_trips
              FROM vehicle_booking b
              JOIN transport_order o ON o.id = b.transport_order_id
             WHERE b.state = 'done'
               AND b.delivery_date BETWEEN %s AND %s
             GROUP BY b.driver_id, b.branch_id
        """, (date_from, ref_date))
        driver_rows = cr.dictfetchall()

        drivers = {}
        branches = {}
        for row in driver_rows:
            trips = row['trips'] or 0
            customer = row['customer_trips'] or 0
            drivers[(row['driver_id'], row['branch_id'])] = {
                'trips': trips,
                'share': (customer / trips) if trips else 0.0,
            }
            branch = branches.setdefault(row['branch_id'], {'trips': 0, 'customer': 0})
            branch['trips'] += trips
            branch['customer'] += customer
        for branch in branches.values():
            branch['share'] = (branch['customer'] / branch['trips']) if branch['trips'] else 0.0

        # ค่ากลางค่าเที่ยว แยกตามประเภทการจัดส่ง + ช่วงระยะทาง (0-20, 20-50, 50-100, 100+)
        cr.execute("""
            SELECT o.delivery_type,
                   WIDTH_BUCKET(COALESCE(b.distance_km, 0), ARRAY[20, 50, 100]) AS band,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY b.travel_expenses) AS median_fee,
                   COUNT(*) AS trips
              FROM vehicle_booking b
              JOIN transport_order o ON o.id = b.transport_order_id
             WHERE b.state = 'done'
               AND b.delivery_date BETWEEN %s AND %s
               AND b.travel_expenses > 0
             GROUP BY 1, 2
        """, (date_from, ref_date))
        fee_median = {(row['delivery_type'], row['band']): (row['median_fee'] or 0.0, row['trips'])
                      for row in cr.dictfetchall()}

        return {'drivers': drivers, 'branches': branches, 'fee_median': fee_median,
                'date_from': date_from, 'ref_date': ref_date}

    @staticmethod
    def _distance_band(distance):
        distance = distance or 0.0
        if distance < 20:
            return 0
        if distance < 50:
            return 1
        if distance < 100:
            return 2
        return 3

    # ------------------------------------------------------------------
    # กฎแต่ละข้อ (อยู่ในไฟล์ fraud_rules.py จะได้อ่าน/แก้เกณฑ์ได้ง่าย)
    # ------------------------------------------------------------------
    @api.model
    def _build_flags(self, booking, order, stats):
        return fraud_rules.build_flags(booking, order, stats, self.env)

    # ------------------------------------------------------------------
    # ตรวจ 1 เที่ยว / หลายเที่ยว
    # ------------------------------------------------------------------
    @api.model
    def analyze_bookings(self, bookings, stats=None, force=False):
        """ตรวจเที่ยวที่ส่งเข้ามา แล้วบันทึกผล (ข้ามใบที่ตรวจแล้ว ถ้าไม่ได้สั่ง force)"""
        Check = self.env['npd.transport.fraud.check'].sudo()
        bookings = bookings.sudo().filtered(lambda b: b.state == 'done')
        if not bookings:
            return Check
        existing = Check.search([('booking_id', 'in', bookings.ids)])
        by_booking = {c.booking_id.id: c for c in existing}
        if not force:
            bookings = bookings.filtered(lambda b: b.id not in by_booking)
            if not bookings:
                return Check

        stats = stats or self._peer_stats()
        results = Check
        for booking in bookings:
            order = booking.transport_order_id
            flags = self._build_flags(booking, order, stats)
            score = sum(flag.get('score', 0) for flag in flags)
            level = 'high' if score >= SCORE_HIGH else ('watch' if score >= SCORE_WATCH else 'ok')
            via_app = bool(getattr(booking, 'has_app_delivery', False)) or (booking.delivery_source or '') == 'app'
            vals = {
                'booking_id': booking.id,
                'booking_name': booking.name or '',
                'transport_order_id': order.id if order else False,
                'order_name': order.name if order else '',
                'branch_id': booking.branch_id.id if booking.branch_id else False,
                'driver_id': booking.driver_id.id if booking.driver_id else False,
                'driver_name': booking.driver_id.name if booking.driver_id else (booking.delivery_employee_name or ''),
                'vehicle_id': booking.vehicle_id.id if booking.vehicle_id else False,
                'partner_id': booking.partner_id.id if booking.partner_id else False,
                'delivery_date': booking.delivery_date,
                'done_datetime': fields.Datetime.now(),
                'delivery_type': (order.delivery_type or '') if order else '',
                'delivery_source': booking.delivery_source or booking.source or '',
                'done_method': 'app' if via_app else 'manual',
                'no_app_done_reason': getattr(booking, 'no_app_done_reason', False) or '',
                'distance_km': booking.distance_km or 0.0,
                'travel_expenses': booking.travel_expenses or 0.0,
                'daily_allowance': booking.daily_allowance or 0.0,
                'shipping_cost': booking.shipping_cost or 0.0,
                'order_trip_allowance': (order.trip_allowance or 0.0) if order else 0.0,
                'order_daily_allowance': (order.daily_allowance or 0.0) if order else 0.0,
                'free_shipping': bool(order and getattr(order, 'use_special_delivery_zero', False)),
                'risk_score': score,
                'risk_level': level,
                'summary': '\n'.join('• %s — %s' % (f['name'], f.get('detail') or '') for f in flags),
                'ai_state': 'pending' if score >= SCORE_AI else 'skipped',
                'flag_ids': [(5, 0, 0)] + [(0, 0, {
                    'code': f['code'], 'name': f['name'], 'severity': f.get('severity', 'medium'),
                    'score': f.get('score', 0), 'detail': f.get('detail') or '',
                    'value': f.get('value') or 0.0, 'baseline': f.get('baseline') or 0.0,
                }) for f in flags],
                'analyzed_date': fields.Datetime.now(),
            }
            check = by_booking.get(booking.id)
            if check:
                check.write(vals)
            else:
                check = Check.create(vals)
            results |= check
        return results

    # ------------------------------------------------------------------
    # AI อธิบายใบที่เข้าข่าย (ทำเป็นรอบ ไม่ถ่วงตอนปิดงาน)
    # ------------------------------------------------------------------
    @api.model
    def _ai_explain(self, checks):
        Gemini = self.env['npd.ai.it.gemini']
        if not Gemini.is_available():
            _logger.info('ตรวจทุจริตการจัดส่ง: ยังไม่ได้ตั้งค่า AI Key ข้ามขั้นตอนวิเคราะห์')
            return False
        for check in checks:
            facts = {
                'เลขที่การจอง': check.booking_name,
                'วันที่จัดส่ง': str(check.delivery_date or ''),
                'สาขา': check.branch_id.name or '',
                'คนขับ': check.driver_name or '',
                'ลูกค้า': check.partner_id.name if check.partner_id else '',
                'ประเภทการจัดส่ง': DELIVERY_TYPE_LABELS.get(check.delivery_type, check.delivery_type or ''),
                'แหล่งที่มา': check.delivery_source,
                'วิธีปิดงาน': 'ผ่านแอป' if check.done_method == 'app' else 'ปิดเองในระบบ',
                'เหตุผลที่ไม่ได้ปิดผ่านแอป': check.no_app_done_reason or '',
                'ระยะทาง_กม': check.distance_km,
                'ค่าเที่ยว': check.travel_expenses,
                'เบี้ยเลี้ยง': check.daily_allowance,
                'ค่าขนส่งที่เก็บลูกค้า': check.shipping_cost,
                'ค่าเที่ยวตาม_odoo14': check.order_trip_allowance,
                'เบี้ยเลี้ยงตาม_odoo14': check.order_daily_allowance,
                'ตั้งไม่คิดค่าขนส่ง': check.free_shipping,
                'ข้อสังเกตจากระบบ': [
                    {'กฎ': flag.name, 'ความรุนแรง': flag.severity, 'รายละเอียด': flag.detail}
                    for flag in check.flag_ids
                ],
                'คะแนนความเสี่ยงจากกฎ': check.risk_score,
            }
            prompt = (
                'คุณเป็นผู้ตรวจสอบภายในของบริษัทให้เช่าอุปกรณ์ก่อสร้างที่มีรถส่งของเอง\n'
                'ข้อมูลเที่ยวจัดส่ง 1 เที่ยว พร้อมข้อสังเกตที่ระบบตรวจเจอ:\n'
                '%s\n\n'
                'บริบทที่ต้องรู้: ประเภทการจัดส่ง "ลูกค้าให้ไปส่ง" จ่ายค่าเที่ยวสูงกว่า "ส่งของสาขา" '
                'พนักงานบางคนจึงอ้างว่าลูกค้าเรียกให้ไปส่ง/ไปรับของ เพื่อให้ได้ค่าเที่ยวเพิ่ม\n\n'
                'ช่วยสรุปเป็นภาษาไทยสั้น ๆ ว่า\n'
                '1. เที่ยวนี้น่าสงสัยเรื่องอะไรบ้าง (อ้างตัวเลขที่เห็น)\n'
                '2. ถ้าจะตรวจต่อ ควรขอหลักฐานหรือถามอะไรกับใคร\n'
                '3. ให้ระดับความเสี่ยงของคุณเอง: ok / watch / high\n\n'
                'ตอบเป็น JSON เท่านั้น: {"severity": "ok|watch|high", '
                '"summary": "สรุปสั้น ๆ 1-3 ประโยค", "checklist": ["สิ่งที่ควรตรวจต่อ", "..."]}'
                % json.dumps(facts, ensure_ascii=False, default=str)
            )
            answer = Gemini.extract_json(prompt, max_output_tokens=1024)
            if not answer:
                check.write({'ai_state': 'error'})
                continue
            severity = answer.get('severity')
            checklist = answer.get('checklist') or []
            body = '<div>%s</div>' % html_escape(str(answer.get('summary') or ''))
            if checklist:
                body += '<div class="mt-2"><b>ควรตรวจต่อ</b><ul class="mb-0 ps-4">%s</ul></div>' % ''.join(
                    '<li>%s</li>' % html_escape(str(item)) for item in checklist)
            check.write({
                'ai_summary': body,
                'ai_severity': severity if severity in ('ok', 'watch', 'high') else False,
                'ai_state': 'done',
                'ai_date': fields.Datetime.now(),
            })
        return True

    # ------------------------------------------------------------------
    # cron
    # ------------------------------------------------------------------
    @api.model
    def cron_ai_explain(self, limit=30):
        """ให้ AI อธิบายใบที่รอคิวอยู่ (ทีละไม่เกิน limit ใบต่อรอบ)"""
        checks = self.env['npd.transport.fraud.check'].sudo().search(
            [('ai_state', '=', 'pending')], order='risk_score desc, id', limit=limit)
        if checks:
            self._ai_explain(checks)
        return True

    @api.model
    def cron_analyze_recent(self, days=3):
        """ตรวจซ้ำเที่ยวที่เพิ่งปิดงาน เผื่อมีใบที่ hook พลาด (เช่นแก้ข้อมูลย้อนหลัง)"""
        date_from = fields.Date.context_today(self) - timedelta(days=days)
        bookings = self.env['vehicle.booking'].sudo().search([
            ('state', '=', 'done'),
            ('delivery_date', '>=', date_from),
        ])
        return self.analyze_bookings(bookings)

    @api.model
    def action_backfill(self, date_from=None, limit=None, force=False):
        """ตรวจย้อนหลังตั้งแต่เดือน 6 (ผู้ใช้ขอให้เก็บสถิติย้อนหลัง)

        เรียกซ้ำได้เรื่อย ๆ — ใบที่ตรวจแล้วจะถูกข้าม (ยกเว้นสั่ง force)
        """
        date_from = date_from or BACKFILL_START
        domain = [('state', '=', 'done'), ('delivery_date', '>=', date_from)]
        bookings = self.env['vehicle.booking'].sudo().search(domain, order='delivery_date, id',
                                                             limit=limit or None)
        stats = self._peer_stats()
        done = self.analyze_bookings(bookings, stats=stats, force=force)
        _logger.info('ตรวจทุจริตการจัดส่ง: ตรวจย้อนหลังตั้งแต่ %s แล้ว %s เที่ยว', date_from, len(done))
        return len(done)

    @api.model
    def action_backfill_button(self):
        """ปุ่มในเมนู: ตรวจย้อนหลังแล้วเปิดรายการให้ดู"""
        count = self.action_backfill()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ตรวจย้อนหลังเรียบร้อย'),
                'message': _('ตรวจเพิ่ม %s เที่ยว (ใบที่ตรวจแล้วถูกข้าม) '
                             'ใบที่เข้าข่ายจะถูกส่งให้ AI วิเคราะห์ในรอบถัดไป') % count,
                'type': 'success',
                'sticky': False,
            },
        }
