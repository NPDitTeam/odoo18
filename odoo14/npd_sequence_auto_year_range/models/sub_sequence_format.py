# -*- coding: utf-8 -*-
"""เดารูปแบบ prefix/suffix ของ Sub Sequence จากค่าที่สร้างไว้แล้ว

ปุ่ม Generate Sub Sequences เก็บแค่ผลลัพธ์ (เช่น "260131") ไม่ได้เก็บรูปแบบ
ที่พิมพ์ไว้ (เช่น "%(y)s%(month)s%(day)s") จึงต้องย้อนกลับจากข้อมูลจริง

รูปแบบ = tuple ของส่วนย่อย ('tok', ชื่อตัวแปร) หรือ ('lit', ข้อความคงที่)
ไม่มี dependency กับ Odoo เพื่อทดสอบแยกได้
"""

import calendar
from datetime import date, timedelta

# ตัวแปรที่รู้จัก -> ข้อความจากวันที่
TOKENS = (
    ('year', lambda d: '%04d' % d.year),
    ('be_year', lambda d: '%04d' % (d.year + 543)),
    ('y', lambda d: '%02d' % (d.year % 100)),
    ('be_y', lambda d: '%02d' % ((d.year + 543) % 100)),
    ('month', lambda d: '%02d' % d.month),
    ('day', lambda d: '%02d' % d.day),
)
TOKEN_FUNCS = dict(TOKENS)

# ยาวกว่านี้ไม่ไล่ทุกแบบ (จำนวนแบบโตแบบทวีคูณ) ถือเป็นข้อความคงที่ทั้งก้อน
MAX_SCAN_LENGTH = 16


def render(fmt, d):
    return ''.join(TOKEN_FUNCS[value](d) if kind == 'tok' else value for kind, value in fmt)


def describe(fmt):
    """แสดงรูปแบบให้คนอ่าน เช่น %(y)s%(month)s%(day)s"""
    if not fmt:
        return '(ว่าง)'
    return ''.join('%%(%s)s' % value if kind == 'tok' else value for kind, value in fmt)


def _decompositions(text, d):
    """ทุกวิธีที่แบ่ง text เป็นตัวแปรของวันที่ d + ข้อความคงที่"""
    if len(text) > MAX_SCAN_LENGTH:
        return [(('lit', text),)]
    values = [(name, func(d)) for name, func in TOKENS]
    results = []

    def walk(pos, parts):
        if pos == len(text):
            results.append(tuple(parts))
            return
        for name, value in values:
            if text.startswith(value, pos):
                walk(pos + len(value), parts + [('tok', name)])
        char = text[pos]
        if parts and parts[-1][0] == 'lit':
            walk(pos + 1, parts[:-1] + [('lit', parts[-1][1] + char)])
        else:
            walk(pos + 1, parts + [('lit', char)])

    walk(0, [])
    return results


def _score(fmt):
    # ใช้ตัวแปรให้มากที่สุด (ข้อความคงที่น้อยสุด) -> ส่วนน้อยสุด -> ค.ศ. ก่อน พ.ศ.
    literal_chars = sum(len(value) for kind, value in fmt if kind == 'lit')
    buddhist = sum(1 for kind, value in fmt if kind == 'tok' and value.startswith('be_'))
    return literal_chars, len(fmt), buddhist


def infer_format(samples):
    """หารูปแบบที่สร้างข้อความของทุกตัวอย่างได้ตรง

    :param samples: list ของ (date, text)
    :return: รูปแบบ (tuple) หรือ None ถ้าไม่มีรูปแบบไหนตรงทุกตัวอย่าง
    """
    texts = [text or '' for _d, text in samples]
    if not any(texts):
        return ()
    # ตัวอย่างตั้งต้น: วันที่ที่ วัน/เดือน/ปี แยกกันชัดที่สุด ลดแบบที่ต้องไล่
    pivot = max(samples, key=lambda s: (s[0].day > 12, s[0].day != s[0].month, s[0]))
    candidates = _decompositions(pivot[1] or '', pivot[0])
    matched = [fmt for fmt in candidates
               if all(render(fmt, d) == (text or '') for d, text in samples)]
    if not matched:
        return None
    return min(matched, key=_score)


def year_periods(year, period):
    """ช่วงวันที่ (date_from, date_to) ทั้งปี ตามชนิดช่วง"""
    if period == 'day':
        start = date(year, 1, 1)
        return [(start + timedelta(days=i),) * 2
                for i in range((date(year, 12, 31) - start).days + 1)]
    if period == 'month':
        return [(date(year, m, 1), date(year, m, calendar.monthrange(year, m)[1]))
                for m in range(1, 13)]
    if period == 'year':
        return [(date(year, 1, 1), date(year, 12, 31))]
    raise ValueError(period)


def detect_period(ranges, year):
    """ชนิดช่วงของชุดข้อมูล ถ้าครบทั้งปีพอดี ('day' / 'month' / 'year') ไม่งั้น None

    :param ranges: list ของ (date_from, date_to)
    """
    spans = sorted(set(ranges))
    for period in ('day', 'month', 'year'):
        if spans == year_periods(year, period):
            return period
    return None
