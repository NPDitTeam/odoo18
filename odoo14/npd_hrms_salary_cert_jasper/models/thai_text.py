# -*- coding: utf-8 -*-
"""ตัวช่วยข้อความภาษาไทยสำหรับหนังสือรับรองเงินเดือน: จำนวนเงินเป็นตัวอักษร / วันที่ พ.ศ. / ระยะเวลา"""
from dateutil.relativedelta import relativedelta

DIGITS = ['ศูนย์', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']
PLACES = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน']
MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
          'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']


def _read_under_million(number):
    text = ''
    digits = str(number)
    size = len(digits)
    for i, ch in enumerate(digits):
        d = int(ch)
        place = size - i - 1
        if d == 0:
            continue
        if place == 1 and d == 1:
            text += 'สิบ'
        elif place == 1 and d == 2:
            text += 'ยี่สิบ'
        elif place == 0 and d == 1 and size > 1:
            text += 'เอ็ด'
        else:
            text += DIGITS[d] + PLACES[place]
    return text


def _read_integer(number):
    if number == 0:
        return DIGITS[0]
    text = ''
    millions, rest = divmod(number, 1000000)
    if millions:
        text += _read_integer(millions) + 'ล้าน'
    if rest:
        text += _read_under_million(rest)
    return text


def baht_text(amount):
    """16230 -> หนึ่งหมื่นหกพันสองร้อยสามสิบบาทถ้วน"""
    amount = round(abs(amount or 0.0), 2)
    baht = int(amount)
    satang = int(round((amount - baht) * 100))
    text = _read_integer(baht) + 'บาท'
    return text + (_read_integer(satang) + 'สตางค์' if satang else 'ถ้วน')


def thai_date(value):
    """2019-07-30 -> 30 กรกฎาคม พ.ศ.2562"""
    if not value:
        return ''
    return '%d %s พ.ศ.%d' % (value.day, MONTHS[value.month - 1], value.year + 543)


def duration_text(start, end):
    """ระยะเวลาทำงาน เช่น 7 ปี 23 วัน (ไม่แสดงหน่วยที่เป็นศูนย์)"""
    if not start or not end or end < start:
        return ''
    diff = relativedelta(end, start)
    parts = []
    if diff.years:
        parts.append('%d ปี' % diff.years)
    if diff.months:
        parts.append('%d เดือน' % diff.months)
    if diff.days or not parts:
        parts.append('%d วัน' % diff.days)
    return ' '.join(parts)
