# -*- coding: utf-8 -*-
# models/__init__.py
# ไฟล์นี้ทำหน้าที่ import ไฟล์ model ทั้งหมดในโฟลเดอร์ models
# ทุกไฟล์ .py ที่เป็น model ต้องถูก import ที่นี่

from . import res_partner  # import ไฟล์ res_partner.py ที่มี model inherit
from . import insurance_chain  # ตัวคำนวณเงินประกันตามสาย SO (ใช้ร่วมกันทั้ง Error และรายงาน)
from . import insurance_chain_report  # รายงานกระทบยอดเงินประกันตามสาย SO
from . import insurance_deposit_docs  # ค่าประกันคงเหลือในหน้าการรับชำระ / คืนเงินประกันค่าเช่า
from . import deposit_overdraw_ext  # ต่อยอดเมนูตรวจสอบเงินประกันการเช่าเบิกเกิน (สาเหตุ + สาย SO)
