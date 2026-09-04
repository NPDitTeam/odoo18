# -*- coding: utf-8 -*-
"""ให้แอปเลือกฐานข้อมูลเองผ่านหัวข้อความ ``X-Odoo-Db``

ทำไมต้องมีไฟล์นี้
-----------------
Odoo เลือกฐานข้อมูล **ก่อน** เข้า controller และมีอยู่สองทางเท่านั้น
(``odoo/http.py`` เมธอด ``get_session``)

1. คำขอมี cookie ที่ผูกฐานไว้แล้ว
2. หรือหลังกรองด้วย ``dbfilter`` แล้วเหลือฐานเดียวในเครื่อง

เซิร์ฟเวอร์ที่มีหลายฐาน (เช่นฝั่งเราที่มีทั้งงานหลักและงานสินเชื่อ
หรือเครื่องที่ปล่อยเช่าให้ลูกค้าหลายราย) จึงตอบ 404 ให้ทุกเส้นทางที่
ยังไม่มี cookie — รวมถึง ``/api/hrms/v1/login`` ที่แอปต้องเรียกเป็นอันดับแรก
แอปเลยล็อกอินไม่ได้เลย

ทางแก้ตามคู่มือคือตั้ง ``dbfilter = ^%d$`` แล้วให้ชื่อโดเมนย่อยตรงกับชื่อฐาน
แต่ชื่อฐานที่มีตัวพิมพ์ใหญ่และขีดล่างอย่าง ``NPD_Logistics`` เอาไปเป็นชื่อโฮสต์ไม่ได้
และการตั้ง ``dbfilter`` ตายตัวก็จะตัดฐานอื่นออกจากเว็บทั้งหมด

ไฟล์นี้จึงเปิดทางที่สาม: ถ้าคำขอ **เป็นเส้นทางของ API แอปเท่านั้น** และแนบ
ชื่อฐานมาด้วย ก็ใช้ชื่อนั้น ส่วนคำขออื่นทุกชนิด (หน้าเว็บ Odoo, API ของระบบอื่น,
ตัวจัดการฐานข้อมูล) ยังทำงานเหมือนเดิมทุกประการ

ขอบเขตและความปลอดภัย
--------------------
* มีผลเฉพาะเส้นทางที่ขึ้นต้นด้วย ``/api/hrms/`` — จำกัดผลกระทบให้แคบที่สุด
* ยอมรับเฉพาะชื่อฐานที่ **มีอยู่จริงและผ่าน dbfilter เดิมอยู่แล้ว**
  จึงเปิดฐานให้ได้ไม่เกินที่ตั้งค่าไว้เดิม
* การยืนยันตัวตนยังเกิดในฐานนั้นตามปกติ (PIN + token ของฐานนั้นเอง)
  การระบุชื่อฐานได้ ไม่ได้แปลว่าเข้าถึงข้อมูลได้
"""
import logging

from odoo import http
from odoo.tools import config

_logger = logging.getLogger(__name__)

# เส้นทางที่อนุญาตให้ระบุฐานเองได้
API_PREFIX = '/api/hrms/'
DB_HEADER = 'X-Odoo-Db'

# เส้นทางที่ต้องวิ่งเข้า "ศูนย์ควบคุม" เสมอ
#
# ตอนเปิดแอปครั้งแรก ผู้ใช้กรอกแค่รหัสองค์กร ยังไม่รู้ว่าองค์กรนั้นอยู่ฐานไหน
# จึงส่งชื่อฐานมาไม่ได้ — ทะเบียนรหัสองค์กรอยู่ที่ฐานศูนย์ควบคุมฐานเดียว
# ระบุชื่อฐานนั้นใน odoo.conf ด้วยบรรทัด  hrms_control_db = NPD_Logistics
CONTROL_PREFIX = '/api/hrms/v1/tenant/'
CONTROL_DB_OPTION = 'hrms_control_db'

_original_db_filter = http.db_filter


def _db_from_request():
    """ชื่อฐานที่ควรใช้กับคำขอนี้ — คืน None ถ้าไม่ใช่คำขอของ API แอป"""
    try:
        request = http.request
        if not request:
            return None
        httprequest = request.httprequest
        path = httprequest.path
        if not path.startswith(API_PREFIX):
            return None
        hint = (httprequest.headers.get(DB_HEADER)
                or httprequest.args.get('db')
                or None)
        if hint:
            return hint
        if path.startswith(CONTROL_PREFIX):
            # ยังไม่รู้ฐาน เพราะเพิ่งกรอกรหัสองค์กร -> ไปถามศูนย์ควบคุม
            return config.get(CONTROL_DB_OPTION) or None
        return None
    except Exception:
        # ไม่มี request ในบริบทนี้ (เช่น cron หรือตอนบูต) — ปล่อยผ่าน
        return None


def db_filter(dbs, host=None):
    hint = _db_from_request()
    if hint:
        allowed = _original_db_filter(dbs, host=host)
        if hint in allowed:
            return [hint]
        _logger.info(
            '[HRMS API] แอปขอฐาน %r แต่ไม่อยู่ในรายการที่เปิดให้ใช้ — ใช้ค่าเดิมแทน',
            hint)
    return _original_db_filter(dbs, host=host)


# ครอบทับครั้งเดียว กันกรณีโมดูลถูกโหลดซ้ำ
if getattr(http.db_filter, '__module__', None) != __name__:
    http.db_filter = db_filter
    _logger.info('[HRMS API] เปิดให้แอประบุฐานข้อมูลผ่านหัวข้อความ %s '
                 'เฉพาะเส้นทาง %s*', DB_HEADER, API_PREFIX)
