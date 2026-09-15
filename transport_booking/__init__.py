# -*- coding: utf-8 -*-
from . import models
from . import controllers
# ต้อง import เข้ามาที่นี่ Odoo ถึงจะหา hook เจอ (มองหาเป็น attribute ของแพ็กเกจ)
# ของเดิมประกาศ 'post_init_hook' ไว้ใน manifest แต่ไม่ได้ import → ติดตั้งไม่ผ่าน
from .post_init_hook import post_init_hook
