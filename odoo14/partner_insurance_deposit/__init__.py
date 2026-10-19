# -*- coding: utf-8 -*-
# __init__.py (ไฟล์หลักของโมดูล)
# ไฟล์นี้ทำหน้าที่ import โฟลเดอร์ย่อยเข้ามาในโมดูล
# เมื่อ Odoo โหลดโมดูลนี้ จะ import ทุกอย่างจากโฟลเดอร์ models

from . import models  # import โฟลเดอร์ models ที่มีไฟล์ model ของเรา
