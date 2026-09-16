# -*- coding: utf-8 -*-
"""กฎที่ใช้ตรวจแต่ละเที่ยว

ที่มาของ "ค่าที่ควรจะเป็น" — สูตรเดียวกับที่ Odoo 14 ใช้คำนวณตอนสร้างใบสั่งขาย
(pfb_npd_tap_shipment_information/models/sale_order.py: _compute_trip_allowance /
 _compute_daily_allowance) คือ

    ระยะทาง < 100 กม.  -> ค่าเที่ยว 45 (4 ล้อ) / 60 (6 ล้อ) / 75 (10 ล้อ) และเบี้ยเลี้ยง 0
    ระยะทาง >= 100 กม. -> ค่าเที่ยว 0 และเบี้ยเลี้ยง 210
    ไม่มีประเภทรถ/ระยะทาง -> 0 ทั้งคู่

สองอย่างนี้ "จ่ายอย่างใดอย่างหนึ่ง" เสมอ ใบที่มีทั้งค่าเที่ยวและเบี้ยเลี้ยงพร้อมกัน
จึงผิดกติกาแน่นอน ไม่ต้องเดา

ส่วนประเภทการจัดส่ง (customer = ลูกค้าให้ไปส่ง / branch = ส่งของสาขา) ไม่ได้เปลี่ยน
ค่าเที่ยวโดยตรง แต่มันสลับต้นทาง-ปลายทาง ทำให้ "ระยะทาง" เปลี่ยน ซึ่งไปเปลี่ยนค่าเที่ยว
และเบี้ยเลี้ยงอีกที นี่คือช่องที่พนักงานอ้างว่าลูกค้าให้ไปส่ง/ไปรับของ
"""
from datetime import timedelta

# ค่าเที่ยวตามประเภทรถ (เทียบจากชื่อประเภทรถแบบเดียวกับฝั่ง o14)
TRIP_RATE_BY_TYPE = (
    ('4 ล้อ', 45.0),
    ('6 ล้อ', 60.0),
    ('10 ล้อ', 75.0),
)
LONG_TRIP_KM = 100.0          # ตั้งแต่ระยะนี้ขึ้นไปจ่ายเบี้ยเลี้ยงแทนค่าเที่ยว
LONG_TRIP_ALLOWANCE = 210.0   # เบี้ยเลี้ยงของเที่ยวไกล
# ระยะทางที่ "เฉียด" เกณฑ์ 100 กม. พอดี — ขยับนิดเดียวก็ได้เบี้ยเลี้ยง 210 แทนค่าเที่ยว 45-75
NEAR_THRESHOLD_KM = 8.0
FAR_DISTANCE_KM = 50.0        # ถือว่าไกลพอที่ควรเก็บค่าขนส่ง
IMPOSSIBLE_SPEED_KMH = 110.0
# คนขับต้องมีเที่ยวอย่างน้อยเท่านี้ถึงเอาสัดส่วนไปเทียบกับสาขาได้
MIN_TRIPS_FOR_SHARE = 10
CUSTOMER_SHARE_GAP = 0.25     # สัดส่วน "ลูกค้าให้ไปส่ง" สูงกว่าสาขาเท่านี้ถือว่าผิดปกติ
DISTANCE_DIFF_RATIO = 0.25    # ระยะทางต่างจากใบสั่งขายเกินเท่านี้ถือว่าน่าสงสัย

DELIVERY_TYPE_LABELS = {
    'customer': 'ลูกค้าให้ไปส่ง',
    'branch': 'ส่งของสาขา',
}


def _fmt(value):
    return '{:,.2f}'.format(value or 0.0)


def describe_time(distance_km, hours):
    """อธิบายเวลาเดินทางเป็นภาษาคน เช่น "ระยะ 113 กม. ส่งถึงใน 12 นาที (เฉลี่ย 560 กม./ชม.)" """
    if not hours or hours <= 0:
        return ''
    if hours < 1:
        spent = '%d นาที' % round(hours * 60)
    elif hours < 24:
        spent = '%.1f ชั่วโมง' % hours
    else:
        spent = '%.1f วัน' % (hours / 24.0)
    if distance_km:
        return 'ระยะ %.1f กม. ใช้เวลา %s (เฉลี่ย %.0f กม./ชม.)' % (
            distance_km, spent, distance_km / hours)
    return 'ใช้เวลา %s' % spent


def build_headline(booking, order, flags, distance, fee, allowance, hours):
    """บรรทัดเดียวที่บอกว่าเที่ยวนี้ผิดปกติตรงไหน (ให้ผู้ตรวจอ่านเข้าใจทันที)"""
    if not flags:
        return 'ไม่พบข้อสังเกต'
    codes = {flag['code'] for flag in flags}
    parts = []

    if 'impossible_speed' in codes or 'time_reversed' in codes:
        text = describe_time(distance, hours)
        parts.append('ส่งเร็วผิดปกติ — %s' % text if text else 'เวลาส่งผิดปกติ')
    elif 'slow_short_trip' in codes or 'cross_day_delivery' in codes:
        parts.append('ใช้เวลานานผิดปกติ — %s' % describe_time(distance, hours))

    if 'rate_mismatch' in codes or 'both_fee_and_allowance' in codes or 'mismatch_o14' in codes:
        where = ('ไม่ตรงเกณฑ์ระยะ %.0f กม.' % distance) if distance else 'ทั้งที่ไม่มีระยะทางในระบบ'
        parts.append('จ่ายค่าเที่ยว %s + เบี้ยเลี้ยง %s %s' % (_fmt(fee), _fmt(allowance), where))
    if 'pay_changed_after_done' in codes:
        parts.append('ยอดถูกแก้หลังปิดงานแล้ว')
    if 'distance_changed' in codes:
        order_km = (order.distance_km or 0.0) if order else 0.0
        parts.append('ระยะทางเปลี่ยนจาก %.0f เป็น %.0f กม.' % (order_km, distance or 0))
    if 'driver_customer_share' in codes:
        parts.append('คนขับอ้าง "ลูกค้าให้ไปส่ง" บ่อยกว่าเพื่อนร่วมสาขามาก')
    if 'shipping_edited' in codes:
        parts.append('ค่าขนส่งถูกแก้จากที่ระบบคิด')
    if 'free_far_delivery' in codes:
        parts.append('ส่ง %.0f กม. แต่ไม่คิดค่าขนส่ง' % (distance or 0))
    if 'backdated_booking' in codes:
        parts.append('สร้างใบจองย้อนหลัง')
    if 'concurrent_double_pay' in codes:
        parts.append('งานซ้อนคันเดียวกันแต่จ่ายสองใบ')

    if not parts:
        # เหลือแต่ข้อสังเกตเบา ๆ
        parts.append(flags[0]['name'])
    return ' · '.join(parts[:3])


def expected_pay(vehicle_type_name, distance_km):
    """คืน (ค่าเที่ยวที่ควรได้, เบี้ยเลี้ยงที่ควรได้, อธิบายเกณฑ์) ตามสูตรของ Odoo 14

    คืน (None, None, '') ถ้าข้อมูลไม่พอให้ตัดสิน (ไม่มีประเภทรถหรือไม่มีระยะทาง)
    """
    distance = distance_km or 0.0
    if distance <= 0:
        return None, None, ''
    if distance >= LONG_TRIP_KM:
        return 0.0, LONG_TRIP_ALLOWANCE, 'ระยะ %.1f กม. (ตั้งแต่ %.0f ขึ้นไป) = เบี้ยเลี้ยง %.0f ไม่มีค่าเที่ยว' % (
            distance, LONG_TRIP_KM, LONG_TRIP_ALLOWANCE)
    name = vehicle_type_name or ''
    for keyword, rate in TRIP_RATE_BY_TYPE:
        if keyword in name:
            return rate, 0.0, 'ระยะ %.1f กม. + รถ%s = ค่าเที่ยว %.0f ไม่มีเบี้ยเลี้ยง' % (distance, keyword, rate)
    return None, None, ''


def build_flags(booking, order, stats, env):
    """คืน list ของข้อสังเกตของเที่ยวนี้ (แต่ละอันเป็น dict)"""
    flags = []
    distance = booking.distance_km or 0.0
    fee = booking.travel_expenses or 0.0
    allowance = booking.daily_allowance or 0.0
    delivery_type = booking.delivery_type or (order.delivery_type if order else '')
    type_label = DELIVERY_TYPE_LABELS.get(delivery_type, delivery_type or '—')
    vehicle_type = booking.vehicle_type_name or (order.vehicle_type_name if order else '')

    # ── R1 จ่ายทั้งค่าเที่ยวและเบี้ยเลี้ยงในเที่ยวเดียว (ผิดกติกาแน่นอน) ──
    if fee > 0 and allowance > 0:
        flags.append({
            'code': 'both_fee_and_allowance',
            'name': 'ได้ทั้งค่าเที่ยวและเบี้ยเลี้ยงในเที่ยวเดียว',
            'severity': 'high', 'score': 30,
            'value': fee + allowance,
            'detail': ('ค่าเที่ยว %s + เบี้ยเลี้ยง %s — ตามกติกาจ่ายได้อย่างใดอย่างหนึ่งเท่านั้น '
                       '(ระยะ < %.0f กม. = ค่าเที่ยว, ตั้งแต่ %.0f กม. = เบี้ยเลี้ยง)'
                       % (_fmt(fee), _fmt(allowance), LONG_TRIP_KM, LONG_TRIP_KM)),
        })

    # ── R2 ยอดไม่ตรงกับสูตรมาตรฐาน ──
    exp_fee, exp_allow, rule_text = expected_pay(vehicle_type, distance)
    if exp_fee is not None:
        diffs = []
        if abs(fee - exp_fee) >= 0.01:
            diffs.append('ค่าเที่ยวจ่าย %s ควรเป็น %s' % (_fmt(fee), _fmt(exp_fee)))
        if abs(allowance - exp_allow) >= 0.01:
            diffs.append('เบี้ยเลี้ยงจ่าย %s ควรเป็น %s' % (_fmt(allowance), _fmt(exp_allow)))
        if diffs:
            over = (fee + allowance) - (exp_fee + exp_allow)
            flags.append({
                'code': 'rate_mismatch',
                'name': 'ยอดไม่ตรงกับเกณฑ์มาตรฐาน',
                'severity': 'high' if over > 0 else 'medium',
                'score': 35 if over > 0 else 15,
                'value': fee + allowance,
                'baseline': exp_fee + exp_allow,
                'detail': '%s · เกณฑ์: %s%s' % (' · '.join(diffs), rule_text,
                                                 ' (จ่ายเกิน %s บาท)' % _fmt(over) if over > 0 else ''),
            })

    # ── R3 ยอดในใบจองไม่ตรงกับที่ซิงก์มาจาก Odoo 14 ──
    if order:
        diffs = []
        if abs(fee - (order.trip_allowance or 0.0)) >= 0.01:
            diffs.append('ค่าเที่ยว %s (Odoo 14 = %s)' % (_fmt(fee), _fmt(order.trip_allowance)))
        if abs(allowance - (order.daily_allowance or 0.0)) >= 0.01:
            diffs.append('เบี้ยเลี้ยง %s (Odoo 14 = %s)' % (_fmt(allowance), _fmt(order.daily_allowance)))
        if diffs:
            flags.append({
                'code': 'mismatch_o14',
                'name': 'ยอดถูกแก้ต่างจากใบสั่งขายฝั่ง Odoo 14',
                'severity': 'high', 'score': 30,
                'value': fee, 'baseline': order.trip_allowance or 0.0,
                'detail': ' · '.join(diffs),
            })

        # ── R4 ระยะทางต่างจากใบสั่งขายมาก (สลับต้นทาง-ปลายทาง/แก้ระยะ) ──
        order_km = order.distance_km or 0.0
        if order_km > 0 and distance > 0:
            ratio = abs(distance - order_km) / order_km
            if ratio >= DISTANCE_DIFF_RATIO and abs(distance - order_km) >= 5:
                crossed = (distance >= LONG_TRIP_KM) != (order_km >= LONG_TRIP_KM)
                flags.append({
                    'code': 'distance_changed',
                    'name': 'ระยะทางต่างจากใบสั่งขาย' + (' และข้ามเกณฑ์จ่ายเงิน' if crossed else ''),
                    'severity': 'high' if crossed else 'medium',
                    'score': 30 if crossed else 15,
                    'value': distance, 'baseline': order_km,
                    'detail': ('ใบจองระบุ %.1f กม. แต่ใบสั่งขายระบุ %.1f กม. (ต่าง %.0f%%)%s'
                               % (distance, order_km, ratio * 100,
                                  ' ทำให้ข้ามเกณฑ์ %.0f กม. ซึ่งเปลี่ยนวิธีจ่ายเงิน' % LONG_TRIP_KM
                                  if crossed else '')),
                })

    # ── R5 อ้าง "ลูกค้าให้ไปส่ง" บ่อยกว่าเพื่อนร่วมสาขามาก ──
    driver_stat = stats['drivers'].get((booking.driver_id.id, booking.branch_id.id)) or {}
    branch_stat = stats['branches'].get(booking.branch_id.id) or {}
    if (delivery_type == 'customer' and driver_stat.get('trips', 0) >= MIN_TRIPS_FOR_SHARE
            and branch_stat.get('trips', 0) >= MIN_TRIPS_FOR_SHARE):
        gap = driver_stat['share'] - branch_stat['share']
        if gap >= CUSTOMER_SHARE_GAP:
            flags.append({
                'code': 'driver_customer_share',
                'name': 'อ้าง "ลูกค้าให้ไปส่ง" บ่อยผิดปกติ',
                'severity': 'high' if gap >= 0.4 else 'medium',
                'score': 25 if gap >= 0.4 else 15,
                'value': round(driver_stat['share'] * 100, 1),
                'baseline': round(branch_stat['share'] * 100, 1),
                'detail': ('คนขับคนนี้ปิดงานเป็น "%s" %.0f%% จาก %s เที่ยว ขณะที่ทั้งสาขาเฉลี่ย %.0f%% '
                           '(ต่างกัน %.0f จุด) ประเภทนี้สลับต้นทาง-ปลายทาง ทำให้ระยะทางและเงินที่ได้ต่างออกไป'
                           % (DELIVERY_TYPE_LABELS['customer'], driver_stat['share'] * 100,
                              driver_stat['trips'], branch_stat['share'] * 100, gap * 100)),
            })

    # ── R6 ระยะทางเฉียดเกณฑ์ 100 กม. พอดี (ขยับนิดเดียวได้เบี้ยเลี้ยง 210) ──
    if LONG_TRIP_KM <= distance <= LONG_TRIP_KM + NEAR_THRESHOLD_KM and allowance > 0:
        flags.append({
            'code': 'near_threshold',
            'name': 'ระยะทางเกินเกณฑ์เบี้ยเลี้ยงมาแบบเฉียดฉิว',
            'severity': 'medium', 'score': 15,
            'value': distance, 'baseline': LONG_TRIP_KM,
            'detail': ('ระยะ %.1f กม. เกิน %.0f กม. มา %.1f กม. ทำให้ได้เบี้ยเลี้ยง %s แทนค่าเที่ยว '
                       'ควรเทียบเส้นทางจริงกับใบสั่งขาย'
                       % (distance, LONG_TRIP_KM, distance - LONG_TRIP_KM, _fmt(allowance))),
        })

    # ── R7 ส่งไกลแต่ไม่คิดค่าขนส่งลูกค้า ──
    free_shipping = bool(order and getattr(order, 'use_special_delivery_zero', False))
    charged = booking.shipping_cost or 0.0
    if distance >= FAR_DISTANCE_KM and (free_shipping or charged <= 0):
        flags.append({
            'code': 'free_far_delivery',
            'name': 'ส่งไกลแต่ไม่คิดค่าขนส่ง',
            'severity': 'medium', 'score': 20,
            'value': distance, 'baseline': FAR_DISTANCE_KM,
            'detail': ('ระยะ %.1f กม. แต่เก็บค่าขนส่ง %s%s'
                       % (distance, _fmt(charged),
                          ' และตั้ง "ไม่คิดค่าขนส่ง" ไว้ในใบสั่งขาย' if free_shipping else '')),
        })

    # ── R8 ปิดงานเองโดยไม่มีหลักฐานจากแอป ──
    via_app = bool(booking.has_app_delivery) or (booking.delivery_source or booking.source or '') == 'app'
    has_proof = bool(booking.delivery_photo or booking.receiver_signature)
    if not via_app or not has_proof:
        missing = []
        if not via_app:
            missing.append('ไม่ได้ปิดงานผ่านแอป')
        if not booking.delivery_photo:
            missing.append('ไม่มีรูปหลักฐานการส่ง')
        if not booking.receiver_signature:
            missing.append('ไม่มีลายเซ็นผู้รับ')
        flags.append({
            'code': 'no_delivery_proof',
            'name': 'ไม่มีหลักฐานการส่งครบ',
            # ที่นี่ปิดงานเองในระบบกันเป็นปกติ (ราว 40% ของเที่ยว) จึงให้น้ำหนักน้อย
            # ใช้เป็นข้อมูลประกอบเวลาใบนั้นมีข้อสังเกตอื่นร่วมด้วย ไม่ใช่ตัวชี้เอง
            'severity': 'low',
            'score': 8 if not via_app and not has_proof else 4,
            'detail': ('%s%s' % (' · '.join(missing),
                                 ' · เหตุผลที่ระบุ: %s' % booking.no_app_done_reason
                                 if booking.no_app_done_reason else ' · ไม่ได้ระบุเหตุผล')),
        })

    # ── R9 เที่ยวซ้อน/เที่ยวซ้ำที่จ่ายเงินซ้ำ ──
    if booking.is_concurrent_booking and fee + allowance > 0:
        twin = booking.concurrent_booking_id
        twin_pay = (twin.travel_expenses or 0.0) + (twin.daily_allowance or 0.0) if twin else 0.0
        if twin_pay > 0:
            flags.append({
                'code': 'concurrent_double_pay',
                'name': 'งานซ้อนคันเดียวกันแต่จ่ายเงินทั้งสองใบ',
                'severity': 'high', 'score': 25,
                'value': fee + allowance, 'baseline': twin_pay,
                'detail': ('เที่ยวนี้ซ้อนกับ %s ซึ่งจ่าย %s บาท ส่วนใบนี้จ่าย %s บาท '
                           'รถและคนขับคันเดียวกันวิ่งรอบเดียว ควรตรวจว่าจ่ายซ้ำหรือไม่'
                           % (twin.name if twin else '-', _fmt(twin_pay), _fmt(fee + allowance))),
            })

    if booking.delivery_date and booking.driver_id and booking.partner_id:
        twins = env['vehicle.booking'].sudo().search_count([
            ('id', '!=', booking.id), ('state', '=', 'done'),
            ('delivery_date', '=', booking.delivery_date),
            ('driver_id', '=', booking.driver_id.id),
            ('partner_id', '=', booking.partner_id.id),
        ])
        if twins:
            flags.append({
                'code': 'duplicate_trip',
                'name': 'เที่ยวซ้ำ วันเดียวกัน ลูกค้าเดียวกัน',
                # ส่งลูกค้ารายเดิมวันละหลายรอบเป็นเรื่องปกติของงานเช่า ให้น้ำหนักน้อย
                'severity': 'low', 'score': 8,
                'value': twins + 1,
                'detail': ('วันที่ %s คนขับคนนี้ส่งลูกค้ารายเดียวกัน %s เที่ยว '
                           'ตรวจว่าแยกใบเพื่อเบิกค่าเที่ยวหลายรอบหรือไม่' % (booking.delivery_date, twins + 1)),
            })

    # ── R10 เวลาผิดธรรมชาติ ──
    pickup = booking.actual_pickup_time or booking.planned_start_date_t
    delivered = booking.actual_delivery_time or booking.delivery_timestamp or booking.planned_end_date_t
    if pickup and delivered and distance > 5:
        hours = (delivered - pickup).total_seconds() / 3600.0
        if -0.034 < hours < 0.034:
            # ต่างกันไม่ถึง 2 นาที = ระบบบันทึกเวลารับกับเวลาส่งพร้อมกันตอนกดปิดงาน
            # ไม่ได้แปลว่าวิ่งเร็วผิดปกติ แต่แปลว่าไม่มีเวลาจริงให้ตรวจ
            flags.append({
                'code': 'no_time_data', 'name': 'ไม่มีเวลารับ-ส่งจริงให้ตรวจ',
                'severity': 'low', 'score': 5,
                'detail': ('เวลาออกเดินทางกับเวลาส่งถึงถูกบันทึกพร้อมกัน (%s) '
                           'ตรวจระยะเวลาเดินทางจริงไม่ได้' % pickup),
            })
        elif hours <= 0:
            flags.append({
                'code': 'time_reversed', 'name': 'เวลาส่งถึงย้อนหลังกว่าเวลาออกเดินทาง',
                'severity': 'high', 'score': 25,
                'detail': ('ออกเดินทาง %s แต่บันทึกว่าส่งถึง %s ซึ่งเป็นเวลาก่อนหน้า '
                           'แปลว่าเวลาถูกกรอกเอง ไม่ได้มาจากการทำงานจริง' % (pickup, delivered)),
            })
        elif distance / hours > IMPOSSIBLE_SPEED_KMH:
            flags.append({
                'code': 'impossible_speed', 'name': 'ระยะทางขนาดนี้ ส่งถึงเร็วเกินกว่าจะเป็นไปได้',
                'severity': 'high', 'score': 25,
                'value': round(distance / hours, 1), 'baseline': IMPOSSIBLE_SPEED_KMH,
                'detail': ('%s — รถบรรทุกวิ่งจริงได้ราว %.0f กม./ชม. '
                           'เวลาที่บันทึกไว้จึงไม่น่าเป็นเวลาที่วิ่งจริง (ออก %s ถึง %s)'
                           % (describe_time(distance, hours), IMPOSSIBLE_SPEED_KMH, pickup, delivered)),
            })

    # ── R11 ยอดถูกแก้หลังปิดงานแล้ว (ค่าเที่ยว/เบี้ยเลี้ยงมี tracking อยู่แล้ว) ──
    changed = _pay_changed_after_done(booking, env)
    if changed:
        flags.append({
            'code': 'pay_changed_after_done',
            'name': 'ยอดถูกแก้หลังปิดงานเสร็จสิ้นแล้ว',
            'severity': 'high', 'score': 30,
            'detail': ' · '.join(changed),
        })

    # ── R12 ค่าขนส่งถูกแก้จากที่ระบบคิดให้ ──
    # ผู้ใช้ระบุ 16 ก.ย. 2569: ระบบคิดค่าขนส่งให้อยู่แล้ว แต่สาขาแก้เองได้
    # โดยอ้างว่าลูกค้าขอลด/อยากได้เลขกลม ๆ ขณะที่ค่าเที่ยวยังจ่ายเท่าเดิม
    # จึงไม่ฟันธงว่าทุจริต แต่ต้องเก็บไว้ดูรูปแบบ (ถ้าซ้ำ ๆ คนเดิม/สาขาเดิม AI จะชี้ให้เอง)
    if order:
        system_cost = order.shipping_cost_m if (order.shipping_cost_m or 0.0) > 0 else (order.shipping_cost or 0.0)
        if not free_shipping and system_cost > 0 and abs(charged - system_cost) >= 1.0:
            diff = charged - system_cost
            ratio = abs(diff) / system_cost
            flags.append({
                'code': 'shipping_edited',
                'name': 'ค่าขนส่งถูกแก้จากที่ระบบคิดให้' + (' (ลดลง)' if diff < 0 else ' (เพิ่มขึ้น)'),
                'severity': 'medium' if ratio >= 0.2 else 'low',
                'score': 15 if ratio >= 0.2 else 10,
                'value': charged, 'baseline': system_cost,
                'detail': ('ระบบคิดไว้ %s บาท แต่เก็บจริง %s บาท (%s %s บาท / %.0f%%) '
                           'ค่าเที่ยวที่จ่ายคนขับยังเท่าเดิม %s บาท'
                           % (_fmt(system_cost), _fmt(charged), 'ลดลง' if diff < 0 else 'เพิ่มขึ้น',
                              _fmt(abs(diff)), ratio * 100, _fmt(fee + allowance))),
            })

    # ── R13 เที่ยวนี้เก็บเงินได้น้อยกว่าที่จ่ายออกไป ──
    trip_cost = fee + allowance + (booking.total_expense or 0.0)
    if not free_shipping and trip_cost > 0 and 0 < charged < trip_cost:
        flags.append({
            'code': 'revenue_below_cost',
            'name': 'ค่าขนส่งที่เก็บได้น้อยกว่าต้นทุนเที่ยว',
            'severity': 'medium', 'score': 15,
            'value': charged, 'baseline': trip_cost,
            'detail': ('เก็บลูกค้า %s บาท แต่จ่ายออก %s บาท (ค่าเที่ยว %s + เบี้ยเลี้ยง %s + ค่าใช้จ่ายอื่น %s) '
                       'ขาดทุนเที่ยวนี้ %s บาท'
                       % (_fmt(charged), _fmt(trip_cost), _fmt(fee), _fmt(allowance),
                          _fmt(booking.total_expense), _fmt(trip_cost - charged))),
        })

    # ── R14 จองย้อนหลัง: สร้างใบจองหลังวันที่ส่งของไปแล้ว ──
    if booking.create_date and booking.delivery_date:
        gap_days = (booking.create_date.date() - booking.delivery_date).days
        if gap_days >= 1:
            flags.append({
                'code': 'backdated_booking',
                'name': 'สร้างใบจองย้อนหลังหลังวันที่ส่งของ',
                'severity': 'high' if gap_days >= 3 else 'medium',
                'score': 25 if gap_days >= 3 else 15,
                'value': gap_days,
                'detail': ('วันที่ส่ง %s แต่ใบจองเพิ่งถูกสร้างเมื่อ %s (หลังไป %s วัน) '
                           'ตรวจว่าเป็นการตามเก็บงานย้อนหลังจริงหรือสร้างขึ้นเพื่อเบิกเงิน'
                           % (booking.delivery_date, booking.create_date, gap_days)),
            })

    # ── R15 เวลารับงาน-ส่งถึง ไม่สมเหตุสมผลกับระยะทาง ──
    if pickup and delivered and 0.034 <= (delivered - pickup).total_seconds() / 3600.0:
        hours = (delivered - pickup).total_seconds() / 3600.0
        # ใช้เวลานานผิดปกติกับระยะทางสั้น (เกิน 8 ชม. สำหรับงานในเมือง)
        if distance and distance < 50 and hours > 8:
            flags.append({
                'code': 'slow_short_trip',
                'name': 'งานระยะใกล้แต่ใช้เวลานานผิดปกติ',
                'severity': 'low', 'score': 8,
                'value': round(hours, 2), 'baseline': 8.0,
                'detail': ('ระยะ %.1f กม. แต่ใช้เวลา %.1f ชม. (รับงาน %s ส่งถึง %s)'
                           % (distance, hours, pickup, delivered)),
            })
        # ส่งข้ามวันโดยที่ไม่ใช่งานไกล
        elif distance and distance < LONG_TRIP_KM and delivered.date() > pickup.date():
            flags.append({
                'code': 'cross_day_delivery',
                'name': 'รับงานวันหนึ่ง ส่งถึงอีกวันหนึ่ง',
                'severity': 'low', 'score': 8,
                'detail': ('รับงาน %s ส่งถึง %s ระยะ %.1f กม. '
                           'ถ้าไม่ใช่งานค้างคืนจริง ควรตรวจว่าเวลาถูกบันทึกถูกต้องไหม'
                           % (pickup, delivered, distance)),
            })

    # ── R16 ไม่มีระยะทางแต่เบิกเงิน ──
    if (fee > 0 or allowance > 0) and distance <= 0:
        flags.append({
            'code': 'missing_distance', 'name': 'ไม่มีระยะทางแต่มีการจ่ายเงิน',
            'severity': 'medium', 'score': 15,
            'value': fee + allowance,
            'detail': 'จ่ายรวม %s บาท แต่ระบบไม่มีระยะทางของเที่ยวนี้ ตรวจไม่ได้ว่าถูกเกณฑ์ไหม' % _fmt(fee + allowance),
        })
    return flags


def _pay_changed_after_done(booking, env):
    """ดูจากประวัติการแก้ไข (mail.tracking.value) ว่าค่าเที่ยว/เบี้ยเลี้ยงถูกแก้หลังปิดงานหรือไม่

    ทั้งสองฟิลด์ตั้ง tracking=True ไว้อยู่แล้ว จึงมีประวัติให้ตรวจ
    """
    done_time = booking.actual_delivery_time or booking.planned_end_date_t
    if not done_time:
        return []
    messages = env['mail.message'].sudo().search([
        ('model', '=', 'vehicle.booking'),
        ('res_id', '=', booking.id),
        ('date', '>', done_time + timedelta(minutes=5)),
    ])
    if not messages:
        return []
    changes = []
    for tracking in messages.mapped('tracking_value_ids'):
        field = tracking.field_id
        if field and field.name in ('travel_expenses', 'daily_allowance'):
            changes.append('%s: %s -> %s (แก้เมื่อ %s)' % (
                field.field_description or field.name,
                _fmt(tracking.old_value_float), _fmt(tracking.new_value_float),
                tracking.mail_message_id.date))
    return changes
