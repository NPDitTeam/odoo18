# -*- coding: utf-8 -*-
"""แก้วันเกิดที่ถูกกรอกเป็นปี พ.ศ. (เช่น 2538-07-27) ให้เป็น ค.ศ.

ก่อนเวอร์ชันนี้ระบบรับปีอะไรก็ได้ วันเกิดปี พ.ศ. จึงถูกเก็บเป็นปี ค.ศ. ในอนาคต
อายุเลยเป็น 0 — เวอร์ชันนี้แปลงให้ตอนบันทึกแล้ว สคริปต์นี้เก็บกวาดข้อมูลเดิม
(เกณฑ์เดียวกับ BE_YEAR_THRESHOLD ในโมเดล: ปีเกิน 2400 = ปี พ.ศ.)
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE employee_salary
           SET birthdate = (birthdate - interval '543 years')::date
         WHERE birthdate >= '2401-01-01'
    """)
    _logger.info('npd_hrms_base: แปลงวันเกิดปี พ.ศ. เป็น ค.ศ. %d รายการ', cr.rowcount)
